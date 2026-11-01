"""
Add / delete AC units, with their ML models, from the dashboard.

Design notes
------------
* Every AC has a stable **device code** (AC1, AC2, ...). That is what the Pi / ESP32
  sends in `ac_unit` and what is stored in `data_gathered`. It never changes.
* The **label** shown on the dashboard is just the unit's position in the list
  (AC1, AC2, ...). Delete the first AC and the old AC2 is shown as AC1 without
  touching a single data row, so the devices keep matching their data.
* Deleting an AC removes its readings (`data_gathered`), its model, its thresholds
  and its learning curve from Supabase, in one transaction. It cannot be undone.
  `telemetry` has no ac_unit column, so live readings are not touched.
"""
import csv
import io
import re
import threading
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from services import limits, ml_per_ac

DDL_UNITS = """CREATE TABLE IF NOT EXISTS ac_units (
    code TEXT PRIMARY KEY,
    position INTEGER NOT NULL,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""

_NUM = re.compile(r"(\d+)$")

# Pages are rendered on every request, so the AC list is cached for a short time.
_cache = {"t": 0.0, "units": None}
_cache_lock = threading.Lock()


def invalidate_cache():
    with _cache_lock:
        _cache["t"] = 0.0
        _cache["units"] = None


def cached_units(get_conn, ttl=30):
    """list_units() with a short cache; returns None if the database is unavailable."""
    with _cache_lock:
        if _cache["units"] is not None and time.time() - _cache["t"] < ttl:
            return _cache["units"]
    try:
        conn = get_conn()
        try:
            units = list_units(conn)
        finally:
            conn.close()
    except Exception as e:
        print(f"[AC] could not load AC list: {e}", flush=True)
        return None
    with _cache_lock:
        _cache["units"], _cache["t"] = units, time.time()
    return units


def _suffix(code):
    m = _NUM.search(code or "")
    return int(m.group(1)) if m else None


# ------------------------------------------------------------------ DB logic
_ready = False


def ensure_all_tables(conn):
    """Create the tables once per process (and add the name column if an older version made the table)."""
    global _ready
    if _ready:
        return
    ml_per_ac.ensure_tables(conn)
    limits.ensure_table(conn)
    cur = conn.cursor()
    cur.execute(DDL_UNITS)
    conn.commit()
    try:
        cur.execute("ALTER TABLE ac_units ADD COLUMN IF NOT EXISTS name TEXT")
        conn.commit()
    except Exception:
        conn.rollback()
    _ready = True


def sync(conn):
    """Register any ac_unit that already has data but is not in ac_units yet."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ac_unit FROM data_gathered WHERE ac_unit IS NOT NULL")
    in_data = {r["ac_unit"] for r in cur.fetchall()}
    cur.execute("SELECT code FROM ac_units")
    known = {r["code"] for r in cur.fetchall()}
    missing = sorted(in_data - known, key=lambda c: (_suffix(c) is None, _suffix(c) or 0, c))
    if missing:
        cur.execute("SELECT COALESCE(MAX(position), 0) AS p FROM ac_units")
        pos = cur.fetchone()["p"]
        for code in missing:
            pos += 1
            cur.execute("INSERT INTO ac_units (code, position) VALUES (%s, %s)", (code, pos))
        conn.commit()


def list_units(conn):
    ensure_all_tables(conn)
    sync(conn)
    cur = conn.cursor()
    cur.execute("SELECT code, name FROM ac_units ORDER BY position ASC")
    unit_rows = cur.fetchall()
    codes = [r["code"] for r in unit_rows]
    names = {r["code"]: r["name"] for r in unit_rows}
    cur.execute("SELECT ac_unit, COUNT(*) AS c FROM data_gathered GROUP BY ac_unit")
    counts = {r["ac_unit"]: r["c"] for r in cur.fetchall()}
    cur.execute("SELECT ac_unit, n_rows, trained_at FROM ac_models")
    models = {r["ac_unit"]: r for r in cur.fetchall()}
    out = []
    for i, code in enumerate(codes):
        m = models.get(code)
        trained = m["trained_at"] if m else None
        out.append({
            "code": code,
            "label": names.get(code) or f"AC{i + 1}",   # your own name, or AC1, AC2... by position
            "name": names.get(code),
            "default_label": f"AC{i + 1}",
            "position": i + 1,
            "readings": counts.get(code, 0),
            "has_model": m is not None,
            "model_rows": m["n_rows"] if m else 0,
            "trained_at": trained.isoformat() if hasattr(trained, "isoformat") else trained,
        })
    return out


def label_map(conn):
    """{device code: dashboard label}; empty if ac_units does not exist yet."""
    try:
        return {u["code"]: u["label"] for u in list_units(conn)}
    except Exception:
        return {}


_NAME_OK = re.compile(r"^[\w .\-()'/&+]{1,40}$")


def rename_unit(conn, code, name):
    """Give an AC your own name. An empty name goes back to AC1, AC2... by position."""
    units = list_units(conn)
    if not any(u["code"] == code for u in units):
        raise LookupError("Unknown AC")
    name = (name or "").strip()
    if name:
        if not _NAME_OK.match(name):
            raise ValueError("Use 1 to 40 letters, numbers, spaces or - _ . ( ) ' / & +")
        low = name.lower()
        for u in units:
            if u["code"] != code and low in (u["label"].lower(), u["code"].lower()):
                raise ValueError(f"'{name}' is already used by another AC")
    cur = conn.cursor()
    cur.execute("UPDATE ac_units SET name = %s WHERE code = %s", (name or None, code))
    conn.commit()
    invalidate_cache()
    return next(u for u in list_units(conn) if u["code"] == code)


def add_unit(conn):
    ensure_all_tables(conn)
    sync(conn)
    cur = conn.cursor()
    cur.execute("SELECT code, position FROM ac_units")
    rows = cur.fetchall()
    nums = [n for n in (_suffix(r["code"]) for r in rows) if n is not None]
    code = f"AC{(max(nums) + 1) if nums else 1}"
    pos = max([r["position"] for r in rows], default=0) + 1
    cur.execute("INSERT INTO ac_units (code, position) VALUES (%s, %s)", (code, pos))
    conn.commit()
    invalidate_cache()
    return next(u for u in list_units(conn) if u["code"] == code)


def delete_unit(conn, code):
    """Delete the unit and everything stored for it. Returns readings deleted."""
    ensure_all_tables(conn)
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM data_gathered WHERE ac_unit = %s", (code,))
        deleted = cur.rowcount
        cur.execute("DELETE FROM ac_models WHERE ac_unit = %s", (code,))
        cur.execute("DELETE FROM ac_threshold_history WHERE ac_unit = %s", (code,))
        cur.execute("DELETE FROM ac_learning_curve WHERE ac_unit = %s", (code,))
        cur.execute("DELETE FROM ac_limits WHERE ac_unit = %s", (code,))
        cur.execute("DELETE FROM ac_health WHERE ac_unit = %s", (code,))
        cur.execute("DELETE FROM ac_units WHERE code = %s", (code,))
        # close the gap: positions 1..n, so the next AC takes the freed label
        cur.execute("SELECT code FROM ac_units ORDER BY position ASC")
        remaining = [r["code"] for r in cur.fetchall()]
        for i, rc in enumerate(remaining, start=1):
            cur.execute("UPDATE ac_units SET position = %s WHERE code = %s", (i, rc))
        # if the setup page was collecting data for this AC, point it at the first one left
        if remaining:
            cur.execute("UPDATE ac_setup SET data_gathering_unit = %s WHERE data_gathering_unit = %s", (remaining[0], code))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    invalidate_cache()
    limits.invalidate(code)
    return deleted


def export_csv(conn, code):
    cols = ["id", "timestamp", "ac_unit", "dht_temp", "dht_humidity", "vibration",
            "ds18b20_temp1", "ds18b20_temp2", "pzem_voltage", "pzem_current", "pzem_power",
            "pzem_energy", "pzem_frequency", "pzem_power_factor", "ac_status", "ac_thermostat"]
    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(cols)} FROM data_gathered WHERE ac_unit = %s ORDER BY id ASC", (code,))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in cur.fetchall():
        w.writerow([r[c] for c in cols])
    return buf.getvalue()


def train_now(get_conn, code, detector):
    """Background job: train one unit, store model + curve, refresh live models."""
    conn = get_conn()
    try:
        df = ml_per_ac.fetch_unit_df(conn, code)
        bundle = ml_per_ac.train_unit(df)
        if bundle is None:
            print(f"[AC] {code}: not enough usable readings to train", flush=True)
            return
        ml_per_ac.save_bundle(conn, code, bundle)
        ml_per_ac.save_curve(conn, code, ml_per_ac.learning_curve(df), bundle["pct"])
        detector.invalidate()
        invalidate_cache()
        print(f"[AC] {code}: trained on {bundle['n_rows']} rows", flush=True)
    except Exception as e:
        print(f"[AC] training {code} failed: {e}", flush=True)
    finally:
        conn.close()


# ------------------------------------------------------------------- routes
def make_router(get_conn, get_admin, detector):
    router = APIRouter(prefix="/api/acs")

    def require_admin(request: Request):
        if not get_admin(request.cookies.get("admin_session")):
            raise HTTPException(status_code=401, detail="Login required")

    def find(conn, code):
        unit = next((u for u in list_units(conn) if u["code"] == code), None)
        if unit is None:
            raise HTTPException(status_code=404, detail="Unknown AC")
        return unit

    @router.get("")
    def get_units(request: Request):
        require_admin(request)
        conn = get_conn()
        try:
            return list_units(conn)
        finally:
            conn.close()

    @router.post("", status_code=201)
    def create_unit(request: Request):
        require_admin(request)
        conn = get_conn()
        try:
            return add_unit(conn)
        finally:
            conn.close()

    @router.delete("/{code}")
    def remove_unit(code: str, request: Request, confirm: str = ""):
        require_admin(request)
        conn = get_conn()
        try:
            unit = find(conn, code)
            if confirm.strip().upper() not in (unit["label"].upper(), unit["code"].upper()):
                raise HTTPException(status_code=400, detail="Type the AC name to confirm deletion")
            deleted = delete_unit(conn, code)
        finally:
            conn.close()
        detector.invalidate()
        return {"status": "deleted", "code": code, "readings_deleted": deleted}

    @router.post("/{code}/train")
    def train_unit_endpoint(code: str, request: Request, background_tasks: BackgroundTasks):
        require_admin(request)
        conn = get_conn()
        try:
            unit = find(conn, code)
        finally:
            conn.close()
        if unit["readings"] < ml_per_ac.MIN_ROWS:
            raise HTTPException(
                status_code=400,
                detail=f"{unit['label']} needs at least {ml_per_ac.MIN_ROWS} readings (has {unit['readings']})",
            )
        background_tasks.add_task(train_now, get_conn, code, detector)
        return {"status": "training started"}

    def limits_payload(conn, code):
        custom = limits.load_custom(conn, code)
        return {"limits": limits.merged(custom), "defaults": limits.DEFAULT_LIMITS,
                "custom": custom is not None, "meta": limits.LIMIT_META}

    @router.put("/{code}/name")
    def rename(code: str, payload: dict, request: Request):
        require_admin(request)
        conn = get_conn()
        try:
            return rename_unit(conn, code, (payload or {}).get("name"))
        except LookupError:
            raise HTTPException(status_code=404, detail="Unknown AC")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            conn.close()

    @router.get("/{code}/limits")
    def get_unit_limits(code: str, request: Request):
        require_admin(request)
        conn = get_conn()
        try:
            find(conn, code)
            return limits_payload(conn, code)
        finally:
            conn.close()

    @router.put("/{code}/limits")
    def set_unit_limits(code: str, payload: dict, request: Request):
        require_admin(request)
        clean, error = limits.validate((payload or {}).get("limits"))
        if error:
            raise HTTPException(status_code=400, detail=error)
        conn = get_conn()
        try:
            find(conn, code)
            limits.save(conn, code, clean)
            return limits_payload(conn, code)
        finally:
            conn.close()

    @router.post("/{code}/limits/reset")
    def reset_unit_limits(code: str, request: Request):
        require_admin(request)
        conn = get_conn()
        try:
            find(conn, code)
            limits.reset(conn, code)
            return limits_payload(conn, code)
        finally:
            conn.close()

    @router.get("/{code}/export.csv")
    def export_unit(code: str, request: Request):
        require_admin(request)
        conn = get_conn()
        try:
            find(conn, code)
            data = export_csv(conn, code)
        finally:
            conn.close()
        return Response(content=data, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{code}_data.csv"'})

    return router
