"""
Per-AC safety limits, editable on the Manage ACs page.

Every AC starts with the DEFAULT_LIMITS below (the 1.5 HP window AC the project began with). Changing
a limit for one AC is stored in Supabase (table `ac_limits`) and used by:
  * the rule engine (what counts as a problem and what the alert says),
  * the instant safety alerts (current, voltage, power),
  * the "readings when the alert fired" panel and the guideline card.
Nothing else needs editing when a different AC is added: set its limits, or train its model.
"""
import json
import math
import threading
import time

DEFAULT_LIMITS = {
    "power":       {"min": 1650, "max": 1860},
    "voltage":     {"min": 225,  "max": 241},
    "current":     {"min": 7.6,  "max": 8.8},
    "output_temp": {"min": 7,    "max": 25},
    "humidity":    {"min": 0,    "max": 80},
    "outlet_temp": {"min": 50,   "max": 61},
    "inlet_temp":  {"min": 8,    "max": 17},
    "vibration":   {"min": 10,   "max": 90},
}

# What the web form shows. `use` says which side matters for that sensor.
LIMIT_META = [
    {"key": "power",       "label": "Power usage",            "unit": "W",  "use": "both", "instant": "max", "step": 10},
    {"key": "voltage",     "label": "Supply voltage",         "unit": "V",  "use": "both", "instant": "max", "step": 1},
    {"key": "current",     "label": "Operating current",      "unit": "A",  "use": "both", "instant": "max", "step": 0.1},
    {"key": "output_temp", "label": "Output temperature",     "unit": "°C", "use": "both", "step": 1},
    {"key": "humidity",    "label": "Output humidity",        "unit": "%",  "use": "max",  "step": 1},
    {"key": "outlet_temp", "label": "Outlet compressor temp", "unit": "°C", "use": "both", "step": 1},
    {"key": "inlet_temp",  "label": "Inlet compressor temp",  "unit": "°C", "use": "both", "step": 1},
    {"key": "vibration",   "label": "Compressor vibration",   "unit": "Hz", "use": "both", "step": 1,
     "min_label": "Not running below"},
]


def merged(overrides=None):
    """DEFAULT_LIMITS with the saved changes of one AC applied on top (floats, unknown keys ignored)."""
    out = {k: dict(v) for k, v in DEFAULT_LIMITS.items()}
    for key, pair in (overrides or {}).items():
        if key in out and isinstance(pair, dict):
            for side in ("min", "max"):
                if side in pair:
                    try:
                        out[key][side] = float(pair[side])
                    except (TypeError, ValueError):
                        pass
    return out


def validate(data):
    """Return (clean limits, error text). `data` is {sensor: {min, max}}; both sides are required."""
    if not isinstance(data, dict):
        return None, "Limits must be an object"
    clean = {}
    for meta in LIMIT_META:
        key = meta["key"]
        pair = data.get(key)
        if not isinstance(pair, dict):
            return None, f"Missing limits for {meta['label']}"
        vals = {}
        for side in ("min", "max"):
            try:
                v = float(pair.get(side))
            except (TypeError, ValueError):
                return None, f"{meta['label']}: {side} must be a number"
            if not math.isfinite(v) or v < 0 or v > 100000:
                return None, f"{meta['label']}: {side} must be between 0 and 100000"
            vals[side] = v
        if vals["min"] >= vals["max"]:
            return None, f"{meta['label']}: the low value must be smaller than the high value"
        clean[key] = vals
    return clean, None


# ------------------------------------------------------------------ database
def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS ac_limits (
        ac_unit TEXT PRIMARY KEY,
        limits TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    conn.commit()


def load_custom(conn, unit):
    """The saved limits of one AC, or None when it uses the defaults."""
    cur = conn.cursor()
    cur.execute("SELECT limits FROM ac_limits WHERE ac_unit = %s", (unit,))
    row = cur.fetchone()
    if not row:
        return None
    try:
        return json.loads(row["limits"])
    except (TypeError, ValueError):
        return None


def save(conn, unit, limits):
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO ac_limits (ac_unit, limits, updated_at) VALUES (%s, %s, now())
           ON CONFLICT (ac_unit) DO UPDATE SET limits = EXCLUDED.limits, updated_at = now()""",
        (unit, json.dumps(limits)),
    )
    conn.commit()
    invalidate(unit)


def reset(conn, unit):
    cur = conn.cursor()
    cur.execute("DELETE FROM ac_limits WHERE ac_unit = %s", (unit,))
    conn.commit()
    invalidate(unit)


# ------------------------------------------------------- cached lookup (alerts)
_cache = {}
_lock = threading.Lock()


def invalidate(unit=None):
    with _lock:
        if unit is None:
            _cache.clear()
        else:
            _cache.pop(unit, None)


def get(get_conn, unit, ttl=30):
    """Limits of one AC for the alert code. Falls back to the defaults if the database is unavailable."""
    now = time.time()
    with _lock:
        hit = _cache.get(unit)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        conn = get_conn()
        try:
            custom = load_custom(conn, unit)
        finally:
            conn.close()
        value = merged(custom)
    except Exception:
        value = merged(None)   # table not created yet, or the database is down
    with _lock:
        _cache[unit] = (now, value)
    return value
