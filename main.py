from fastapi import FastAPI, Header, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import os
import hmac
import time

LOCAL_TZ = timezone(timedelta(hours=8))
import subprocess
import threading
from database import get_db_connection
from ac_setup import get_ac_setup, update_ac_setup
from web_routes import router as web_router, _read_template
from services.contacts_api import router as contacts_router
from services.alerts_api import router as alerts_router
from services.traccar_setup_api import router as traccar_setup_router
from services.ai_setup_api import router as ai_setup_router

from services import ml_per_ac, ac_manager, ntfy_notifier, action_guide
from services import limits as limits_store
from services.anomaly_reciever import process_anomaly
from services.auth import get_admin_from_token, verify_password, generate_session, clear_session

app = FastAPI(title="AirBnBrrr")

app.mount("/assets", StaticFiles(directory="assets"), name="assets")

app.include_router(web_router)
app.include_router(contacts_router)
app.include_router(alerts_router)
app.include_router(traccar_setup_router)
app.include_router(ai_setup_router)

# One Isolation Forest per AC unit, loaded from Supabase (train with train_models.py or the AC manager page)
detector = ml_per_ac.LiveDetector(get_db_connection)
app.include_router(ac_manager.make_router(get_db_connection, get_admin_from_token, detector))

class Telemetry(BaseModel):
	ac_unit: Optional[str] = None
	dust_sensor: Optional[float] = None
	dht_temp: Optional[float] = None
	dht_humidity: Optional[float] = None
	vibration: Optional[float] = None
	ds18b20_temp1: Optional[float] = None
	ds18b20_temp2: Optional[float] = None
	pzem_voltage: Optional[float] = None
	pzem_current: Optional[float] = None
	pzem_power: Optional[float] = None
	pzem_energy: Optional[float] = None
	pzem_frequency: Optional[float] = None
	pzem_power_factor: Optional[float] = None
	ac_status: Optional[str] = None
	ac_thermostat: Optional[str] = None

class ACSetup(BaseModel):
	ac_status: Optional[str] = None
	ac_thermostat: Optional[str] = None
	data_gathering_mode: Optional[str] = None
	data_gathering_unit: Optional[str] = None

class LoginRequest(BaseModel):
	username: str
	password: str

@app.post("/api/login")
def api_login(payload: LoginRequest, response: Response):
	conn = get_db_connection()
	cur = conn.cursor()
	cur.execute("SELECT password FROM admin WHERE username = %s", (payload.username,))
	row = cur.fetchone()
	conn.close()

	if not row:
		raise HTTPException(status_code=401, detail="Invalid username or password")

	hashed = row["password"]
	if not verify_password(payload.password, hashed):
		raise HTTPException(status_code=401, detail="Invalid username or password")

	token, _ = generate_session(payload.username)
	response.set_cookie(
		key="admin_session",
		value=token,
		httponly=True,
		max_age=86400,
		samesite="lax",
	)
	return {"status": "success"}

@app.post("/api/logout")
@app.get("/api/logout")
def api_logout(request: Request, response: Response):
	token = request.cookies.get("admin_session")
	if token:
		clear_session(token)
	response.delete_cookie("admin_session")
	return RedirectResponse(url="/pages/login", status_code=303)

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
	token = request.cookies.get("admin_session")
	if not get_admin_from_token(token):
		return RedirectResponse(url="/pages/login", status_code=303)
	return HTMLResponse(_read_template("control_panel.html"))


# --- ALERT STATE ---
# Every AC has its own timer and cooldowns, so one unit can never cancel or delay another's alert.
alert_state = {}
state_lock = threading.Lock()

CRITICAL_COOLDOWN = 300   # 5 minutes
BASIC_COOLDOWN = 900      # 15 minutes

# --- SAFETY LIMITS: per AC, edited on the Manage ACs page (defaults = the original 1.5 HP numbers) ---
def limit_sets(L):
    """(always alert, only escalate) lists built from one AC's limits."""
    always = [  # alert immediately, whatever the model says (electrical safety)
        ("pzem_current", L["current"]["max"], "Current", "A", False),
        ("pzem_voltage", L["voltage"]["max"], "Voltage", "V", False),
        ("pzem_power", L["power"]["max"], "Power", "W", False),
    ]
    escalate = [  # only make an alert CRITICAL (instant) when the model has already flagged the AC
        ("vibration", L["vibration"]["max"], "Vibration", "", True),
        ("ds18b20_temp1", L["outlet_temp"]["max"], "Outlet compressor temperature", "C", False),
        ("ds18b20_temp2", L["inlet_temp"]["max"], "Inlet compressor temperature", "C", False),
    ]
    return always, escalate


REQUIRED_SENSORS = ["dht_temp", "dht_humidity", "pzem_voltage", "pzem_current", "ds18b20_temp1", "ds18b20_temp2", "vibration"]


def limit_breaches(payload_dict, limits):
    """Readable sentences for every limit that is broken in the raw numbers."""
    out = []
    for key, limit, name, unit, inclusive in limits:
        try:
            v = float(payload_dict.get(key))
        except (TypeError, ValueError):
            continue
        if v and (v >= limit if inclusive else v > limit):
            out.append((f"{name} is {v:g} {unit}".rstrip()) + (f", limit is {limit:g} {unit}".rstrip()))
    return out


def offline_sensors(payload_dict):
    return [f"Sensor offline: {key}" for key in REQUIRED_SENSORS if payload_dict.get(key) is None]


def _get_state(unit):
    st = alert_state.get(unit)
    if st is None:
        st = alert_state[unit] = {"timer": None, "payload": None, "problems": [], "findings": [], "ml": None, "limits": None,
                                  "last_critical": 0.0, "last_basic": 0.0, "alerted": False}
    return st


def _unit_title(unit):
    """'AC1 (device code AC2)' when the dashboard label differs from the device code."""
    label = None
    try:
        units = ac_manager.cached_units(get_db_connection) or []
        label = next((u["label"] for u in units if u["code"] == unit), None)
    except Exception:
        pass
    if label and label != unit:
        return f"{label} (device code {unit})"
    return label or unit


def trigger_alert_action(unit, is_critical):
    now = time.time()
    with state_lock:
        st = _get_state(unit)
        st["timer"] = None
        data = dict(st["payload"] or {})
        problems = list(st["problems"])
        findings = list(st["findings"])
        ml = st["ml"]
        unit_limits = st["limits"]
        key, cooldown = ("last_critical", CRITICAL_COOLDOWN) if is_critical else ("last_basic", BASIC_COOLDOWN)
        if now - st[key] < cooldown:
            print(f"\n[COOLDOWN] {unit}: {'critical' if is_critical else 'basic'} alert ignored. Waiting {cooldown/60:.0f} mins between alerts.", flush=True)
            return
        st[key] = now
        st["alerted"] = True

    unit_title = _unit_title(unit)
    print(f"\n[PROCESSING] {unit}: firing {'CRITICAL' if is_critical else 'BASIC'} alert (ntfy + SMS)...", flush=True)
    # 1) ntfy: ONE notification listing every problem found on this AC
    try:
        ntfy_notifier.send_alert(unit_title, is_critical, problems, data, action_guide.short_actions(findings, ml))
    except Exception as e:
        print(f"\n[ERROR] ntfy failed: {e}\n", flush=True)
    # 2) SMS + saved alert (unchanged)
    try:
        data["_ml"] = ml   # saved with the alert so the alert page can show what the model found odd
        data["_limits"] = unit_limits   # this AC's own limits, used for the alert text
        data["_title"] = unit_title     # AC name and urgency, used for the SMS text
        data["_critical"] = is_critical
        process_anomaly(data)
    except Exception as e:
        print(f"\n[ERROR] process_anomaly failed: {e}\n", flush=True)


_last_health_log = {}


def _log_health(unit, ml):
	"""Keep one health point per AC per minute: the model's score minus its alert line (above 0 = normal).
	This is what the Model Health page draws, and what the early-warning trend is computed from."""
	now = time.time()
	if now - _last_health_log.get(unit, 0) < 60:
		return
	_last_health_log[unit] = now
	try:
		conn = get_db_connection()
		try:
			try:
				ml_per_ac.log_health(conn, unit, ml["score"] - ml["threshold"], ml["is_anomaly"])
			except Exception:
				conn.rollback()
				ml_per_ac.ensure_tables(conn)   # first run: create the table, then try once more
				ml_per_ac.log_health(conn, unit, ml["score"] - ml["threshold"], ml["is_anomaly"])
			if now - _last_health_log.get("_prune", 0) > 86400:
				_last_health_log["_prune"] = now
				ml_per_ac.prune_health(conn)
		finally:
			conn.close()
	except Exception as e:
		print(f"[ML] could not log health: {e}", flush=True)


def process_telemetry_background(payload_dict: dict):
	try:
		ac_values = get_ac_setup()
		ac_status = ac_values.get("ac_status", "Not Set")
		ac_thermostat = ac_values.get("ac_thermostat", "Not Set")
		data_gathering_mode = ac_values.get("data_gathering_mode", "telemetry")
		data_gathering_unit = payload_dict.get("ac_unit") or ac_values.get("data_gathering_unit", "AC2")

		conn = get_db_connection()
		cur = conn.cursor()
		if data_gathering_mode == "data_gathered":
			cur.execute(
				"""
				INSERT INTO data_gathered (
					timestamp, ac_unit, dust_sensor, dht_temp, dht_humidity, vibration,
					ds18b20_temp1, ds18b20_temp2, pzem_voltage, pzem_current, pzem_power, pzem_energy,
					pzem_frequency, pzem_power_factor, ac_status, ac_thermostat
				) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
				""",
				(datetime.now(LOCAL_TZ), data_gathering_unit, payload_dict.get("dust_sensor"), payload_dict.get("dht_temp"), payload_dict.get("dht_humidity"), payload_dict.get("vibration"), payload_dict.get("ds18b20_temp1"), payload_dict.get("ds18b20_temp2"), payload_dict.get("pzem_voltage"), payload_dict.get("pzem_current"), payload_dict.get("pzem_power"), payload_dict.get("pzem_energy"), payload_dict.get("pzem_frequency"), payload_dict.get("pzem_power_factor"), ac_status, ac_thermostat),
			)
			row_id = cur.fetchone()['id']
			print(f"\n[BACKGROUND] Stored in data_gathered with ID {row_id}", flush=True)
		else:
			cur.execute(
				"""
				INSERT INTO telemetry (
					timestamp, dust_sensor, dht_temp, dht_humidity, vibration,
					ds18b20_temp1, ds18b20_temp2, pzem_voltage, pzem_current, pzem_power, pzem_energy,
					pzem_frequency, pzem_power_factor, ac_status, ac_thermostat
				) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
				""",
				(datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"), payload_dict.get("dust_sensor"), payload_dict.get("dht_temp"), payload_dict.get("dht_humidity"), payload_dict.get("vibration"), payload_dict.get("ds18b20_temp1"), payload_dict.get("ds18b20_temp2"), payload_dict.get("pzem_voltage"), payload_dict.get("pzem_current"), payload_dict.get("pzem_power"), payload_dict.get("pzem_energy"), payload_dict.get("pzem_frequency"), payload_dict.get("pzem_power_factor"), ac_status, ac_thermostat),
			)
			row_id = cur.fetchone()['id']
			print(f"\n[BACKGROUND] Stored in telemetry with ID {row_id}", flush=True)
		conn.commit()
		conn.close()
	except Exception as db_err:
		print(f"\n[ERROR] Failed to save telemetry: {db_err}", flush=True)
		return

	# --- SMART DEBOUNCER LOGIC (one timer per AC) ---
	from services.rule_engine import analyze_with_rules
	unit_limits = limits_store.get(get_db_connection, data_gathering_unit)
	rule_result = analyze_with_rules(payload_dict, unit_limits)
	has_rule_violation = len(rule_result["findings"]) > 0

	always_limits, escalate_limits = limit_sets(unit_limits)
	hard = limit_breaches(payload_dict, always_limits) + offline_sensors(payload_dict)
	soft = limit_breaches(payload_dict, escalate_limits)

	model_data = dict(payload_dict)
	model_data.pop("ac_status", None)
	model_data.pop("ac_thermostat", None)

	try:
		# The per-AC model decides. A unit with no model yet falls back to the rule engine.
		ml = detector.check(data_gathering_unit, model_data)
		model_flag = has_rule_violation if ml is None else ml["is_anomaly"]
		is_anom = model_flag or bool(hard)
		has_critical = bool(hard) or (model_flag and bool(soft))
		if ml:
			print(f"[ML] {data_gathering_unit} score={ml['score']:.3f} threshold={ml['threshold']:.3f} odd={ml['top_features']}", flush=True)
			_log_health(data_gathering_unit, ml)

		if is_anom:
			payload_dict["ac_status"] = ac_status
			payload_dict["ac_thermostat"] = ac_thermostat
			problems = ntfy_notifier.build_problems(hard + soft, rule_result["findings"], ml)

			new_timer = None
			with state_lock:
				st = _get_state(data_gathering_unit)
				st["payload"] = dict(payload_dict)   # newest readings and problems win,
				st["problems"] = problems            # so the alert describes the AC as it is right now
				st["findings"] = rule_result["findings"]
				st["ml"] = ml
				st["limits"] = unit_limits
				if has_critical:
					if st["timer"] is not None:
						st["timer"].cancel()
						st["timer"] = None
				elif st["timer"] is None:
					# Delay basic alerts by 8 minutes (2 minutes once this AC has alerted before)
					delay = 480.0 if not st["alerted"] else 120.0
					new_timer = threading.Timer(delay, trigger_alert_action, [data_gathering_unit, False])
					st["timer"] = new_timer

			if has_critical:
				print(f"\n[SMART DEBOUNCER] {data_gathering_unit}: INSTANT ALERT TRIGGERED (Critical).", flush=True)
				trigger_alert_action(data_gathering_unit, True)
			elif new_timer is not None:
				print(f"\n[SMART DEBOUNCER] {data_gathering_unit}: basic anomaly. Starting {new_timer.interval}s delay...", flush=True)
				new_timer.start()
		else:
			pending = None
			with state_lock:
				st = alert_state.get(data_gathering_unit)
				if st and st["timer"] is not None:
					pending, st["timer"] = st["timer"], None
			if pending is not None:
				print(f"\n[SMART DEBOUNCER] {data_gathering_unit}: telemetry normal. Canceling pending alert.", flush=True)
				pending.cancel()
	except Exception as ml_err:
		print(f"\n[ERROR] Anomaly detection failed: {ml_err}", flush=True)


def _check_device_key(x_api_key):
	"""Only your ESP32 may post readings. Set TELEMETRY_API_KEY on Render; the ESP32 sends the same text
	in the X-API-Key header. With no TELEMETRY_API_KEY set, the check is off (as before)."""
	expected = os.environ.get("TELEMETRY_API_KEY", "")
	if expected and not hmac.compare_digest((x_api_key or "").encode(), expected.encode()):
		raise HTTPException(status_code=401, detail="Invalid device key")


@app.post("/telemetry", status_code=201)
def receive_telemetry(payload: Telemetry, background_tasks: BackgroundTasks, x_api_key: Optional[str] = Header(None)):
	_check_device_key(x_api_key)
	payload_dict = payload.dict()
	background_tasks.add_task(process_telemetry_background, payload_dict)
	return {"status": "stored"}


def get_year_month_day(timestamp):
	if isinstance(timestamp, datetime):
		return timestamp.year, timestamp.month, timestamp.day
	elif isinstance(timestamp, str):
		try:
			dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
			return dt.year, dt.month, dt.day
		except Exception:
			return int(timestamp[:4]), int(timestamp[5:7]), int(timestamp[8:10])
	else:
		now = datetime.now(LOCAL_TZ)
		return now.year, now.month, now.day


@app.get("/telemetry")
def get_telemetry(start: Optional[str] = None, end: Optional[str] = None, ac_unit: Optional[str] = 'telemetry'):
	start_param = None
	end_param = None
	try:
		if start is not None:
			start_dt = datetime.fromisoformat(start)
			start_param = start_dt.strftime("%Y-%m-%d %H:%M:%S")
		if end is not None:
			end_dt = datetime.fromisoformat(end)
			end_param = end_dt.strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601.")

	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit == 'telemetry' or not ac_unit:
		query = "SELECT * FROM telemetry"
		clauses = []
		params = []
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	else:
		query = "SELECT * FROM data_gathered"
		clauses = ["ac_unit = %s"]
		params = [ac_unit]
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	cur.execute(query, params)
	rows = cur.fetchall()

	results = []
	if rows:
		ymd_pairs = set()
		for r in rows:
			ymd_pairs.add(get_year_month_day(r["timestamp"]))
		
		starts = {}
		for y, m, d in ymd_pairs:
			start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
			if ac_unit == 'telemetry' or not ac_unit:
				cur.execute("SELECT pzem_energy FROM telemetry WHERE timestamp >= %s ORDER BY timestamp ASC LIMIT 1", (start_str,))
			else:
				cur.execute("SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1", (start_str, ac_unit))
			start_row = cur.fetchone()
			starts[(y, m, d)] = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0

		for r in rows:
			d_dict = dict(r)
			y, m, d = get_year_month_day(d_dict["timestamp"])
			e_start = starts.get((y, m, d), 0.0)
			if d_dict.get("pzem_energy") is not None:
				d_dict["pzem_energy"] = max(0.0, (d_dict["pzem_energy"] - e_start) / 1000.0)
			results.append(d_dict)
	conn.close()
	return results


@app.get("/telemetry/column")
def telemetry_column(column: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None, ac_unit: Optional[str] = 'telemetry'):
	if not column:
 		raise HTTPException(status_code=400, detail="Missing 'column' query parameter")
		
	allowed = {"id", "timestamp", "dht_temp", "dht_humidity", "vibration", "ds18b20_temp1", "ds18b20_temp2", "pzem_voltage", "pzem_current", "pzem_power", "pzem_energy", "pzem_frequency", "pzem_power_factor", "ac_status", "ac_thermostat"}
	if column not in allowed:
		raise HTTPException(status_code=400, detail="Invalid column requested")

	start_param = None
	end_param = None
	try:
		if start is not None:
			start_dt = datetime.fromisoformat(start)
			start_param = start_dt.strftime("%Y-%m-%d %H:%M:%S")
		if end is not None:
			end_dt = datetime.fromisoformat(end)
			end_param = end_dt.strftime("%Y-%m-%d %H:%M:%S")
	except Exception:
		raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601.")

	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit == 'telemetry' or not ac_unit:
		query = f"SELECT timestamp, {column} FROM telemetry"
		clauses = []
		params = []
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	else:
		query = f"SELECT timestamp, {column} FROM data_gathered"
		clauses = ["ac_unit = %s"]
		params = [ac_unit]
		if start_param is not None:
			clauses.append("timestamp >= %s")
			params.append(start_param)
		if end_param is not None:
			clauses.append("timestamp <= %s")
			params.append(end_param)
		if clauses:
			query += " WHERE " + " AND ".join(clauses)
		query += " ORDER BY id ASC"
	cur.execute(query, params)
	rows = cur.fetchall()

	results = []
	if rows:
		if column == "pzem_energy":
			ymd_pairs = set()
			for r in rows:
				ymd_pairs.add(get_year_month_day(r["timestamp"]))
			
			starts = {}
			for y, m, d in ymd_pairs:
				start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
				if ac_unit == 'telemetry' or not ac_unit:
					cur.execute("SELECT pzem_energy FROM telemetry WHERE timestamp >= %s ORDER BY timestamp ASC LIMIT 1", (start_str,))
				else:
					cur.execute("SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1", (start_str, ac_unit))
				start_row = cur.fetchone()
				starts[(y, m, d)] = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0
			
			for r in rows:
				y, m, d = get_year_month_day(r["timestamp"])
				e_start = starts.get((y, m, d), 0.0)
				val = r[column]
				if val is not None:
					val = max(0.0, (val - e_start) / 1000.0)
				results.append({"timestamp": r["timestamp"], column: val})
		else:
			for r in rows:
				results.append({"timestamp": r["timestamp"], column: r[column]})
	conn.close()
	return results


@app.get("/telemetry/latest")
def latest_telemetry(ac_unit: Optional[str] = 'telemetry'):
	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit == 'telemetry' or not ac_unit:
		cur.execute("SELECT * FROM telemetry ORDER BY id DESC LIMIT 1")
	else:
		cur.execute("SELECT * FROM data_gathered WHERE ac_unit = %s ORDER BY id DESC LIMIT 1", (ac_unit,))
	row = cur.fetchone()
	if not row:
		conn.close()
		raise HTTPException(status_code=404, detail="No telemetry available")
	
	data = dict(row)
	ts = data.get("timestamp")
	y, m, d = get_year_month_day(ts)
	start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
	if ac_unit == 'telemetry' or not ac_unit:
		cur.execute("SELECT pzem_energy FROM telemetry WHERE timestamp >= %s ORDER BY timestamp ASC LIMIT 1", (start_str,))
	else:
		cur.execute("SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1", (start_str, ac_unit))
	start_row = cur.fetchone()
	conn.close()
	
	e_start = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0
	if data.get("pzem_energy") is not None:
		data["pzem_energy"] = max(0.0, (data["pzem_energy"] - e_start) / 1000.0)
	return data


@app.get("/api/historical_data")
def get_historical_data(start: Optional[str] = None, end: Optional[str] = None):
	conn = get_db_connection()
	cur = conn.cursor()
	query = "SELECT * FROM historical_data"
	clauses = []
	params = []
	if start:
		clauses.append("date >= %s")
		params.append(start)
	if end:
		clauses.append("date <= %s")
		params.append(end)
	if clauses:
		query += " WHERE " + " AND ".join(clauses)
	query += " ORDER BY date ASC"
	cur.execute(query, params)
	rows = cur.fetchall()
	conn.close()

	result = []
	for r in rows:
		d = dict(r)
		if d.get("date") and not isinstance(d["date"], str):
			d["date"] = d["date"].strftime("%Y-%m-%d")
		result.append(d)
	return result


@app.get("/data_gathered")
def get_data_gathered(ac_unit: Optional[str] = None):
	conn = get_db_connection()
	cur = conn.cursor()
	if ac_unit:
		cur.execute("SELECT * FROM data_gathered WHERE ac_unit = %s ORDER BY timestamp DESC LIMIT 2000", (ac_unit,))
	else:
		cur.execute("SELECT * FROM data_gathered ORDER BY timestamp DESC LIMIT 2000")
	rows = cur.fetchall()

	results = []
	if rows:
		ymd_ac_pairs = set()
		for r in rows:
			y, m, d = get_year_month_day(r["timestamp"])
			ymd_ac_pairs.add((y, m, d, r["ac_unit"]))

		starts = {}
		for y, m, d, ac in ymd_ac_pairs:
			start_str = f"{y:04d}-{m:02d}-{d:02d} 00:00:00"
			cur.execute("SELECT pzem_energy FROM data_gathered WHERE timestamp >= %s AND ac_unit = %s ORDER BY timestamp ASC LIMIT 1", (start_str, ac))
			start_row = cur.fetchone()
			starts[(y, m, d, ac)] = start_row['pzem_energy'] if (start_row and start_row['pzem_energy'] is not None) else 0.0

		for r in rows:
			d_dict = dict(r)
			y, m, d = get_year_month_day(d_dict["timestamp"])
			ac = d_dict["ac_unit"]
			e_start = starts.get((y, m, d, ac), 0.0)
			if d_dict.get("pzem_energy") is not None:
				d_dict["pzem_energy"] = max(0.0, (d_dict["pzem_energy"] - e_start) / 1000.0)
			results.append(d_dict)
	conn.close()
	return results


@app.post("/data_gathered", status_code=201)
def save_data_gathered(payload: Telemetry, x_api_key: Optional[str] = Header(None)):
	_check_device_key(x_api_key)
	conn = get_db_connection()
	cur = conn.cursor()
	payload_dict = payload.dict()
	ac_unit = payload_dict.get("ac_unit") or "AC2"
	cur.execute(
		"""
		INSERT INTO data_gathered (
			timestamp, ac_unit, dust_sensor, dht_temp, dht_humidity, vibration,
			ds18b20_temp1, ds18b20_temp2, pzem_voltage, pzem_current, pzem_power, pzem_energy,
			pzem_frequency, pzem_power_factor, ac_status, ac_thermostat
		) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
		""",
		(datetime.now(LOCAL_TZ), ac_unit, payload_dict.get("dust_sensor"), payload_dict.get("dht_temp"), payload_dict.get("dht_humidity"), payload_dict.get("vibration"), payload_dict.get("ds18b20_temp1"), payload_dict.get("ds18b20_temp2"), payload_dict.get("pzem_voltage"), payload_dict.get("pzem_current"), payload_dict.get("pzem_power"), payload_dict.get("pzem_energy"), payload_dict.get("pzem_frequency"), payload_dict.get("pzem_power_factor"), payload_dict.get("ac_status"), payload_dict.get("ac_thermostat"))
	)
	row_id = cur.fetchone()['id']
	conn.commit()
	conn.close()
	return {"status": "stored", "id": row_id}


@app.get("/ac_setup")
def read_ac_setup():
	return get_ac_setup()


@app.post("/ac_setup")
def set_ac_setup(payload: ACSetup):
	ac_values = get_ac_setup()
	ac_status = payload.ac_status if payload.ac_status is not None else ac_values.get("ac_status", "Not Set")
	ac_thermostat = payload.ac_thermostat if payload.ac_thermostat is not None else ac_values.get("ac_thermostat", "Not Set")
	data_gathering_mode = payload.data_gathering_mode if payload.data_gathering_mode is not None else ac_values.get("data_gathering_mode", "telemetry")
	data_gathering_unit = payload.data_gathering_unit if payload.data_gathering_unit is not None else ac_values.get("data_gathering_unit", "AC2")
	update_ac_setup(ac_status, ac_thermostat, data_gathering_mode, data_gathering_unit)
	return {"status": "updated", "ac_status": ac_status, "ac_thermostat": ac_thermostat, "data_gathering_mode": data_gathering_mode, "data_gathering_unit": data_gathering_unit}


def _delayed_shutdown() -> None:
	time.sleep(1)
	try:
		subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
	except Exception:
		os.system("shutdown -h now")


@app.post("/system/shutdown")
def shutdown_system(request: Request):
	if not get_admin_from_token(request.cookies.get("admin_session")):
		raise HTTPException(status_code=401, detail="Login required")
	threading.Thread(target=_delayed_shutdown, daemon=True).start()
	return {"status": "accepted", "message": "Shutdown command sent."}


@app.get("/api/isolation_forest/scatter")
def get_isolation_forest_scatter(ac_unit: Optional[str] = None, limit: int = 500):
	"""2D scatter for the Isolation Forest page; every AC is scored by its own model."""
	conn = get_db_connection()
	try:
		return ml_per_ac.scatter_from_db(conn, detector.get_bundles(), ac_unit or None, max(10, min(limit, 2000)))
	except Exception as e:
		return {"error": str(e), "points": [], "stats": {"total": 0, "regular": 0, "abnormal": 0, "contamination": 0.01}}
	finally:
		conn.close()


@app.get("/api/ml/overview")
def ml_overview(ac_unit: str):
	"""Everything the Model Health page shows for one AC, from real data only."""
	from datetime import timedelta
	out = {"ac_unit": ac_unit, "model": None, "profile": [], "health": [], "latest": None, "trend": None, "learning": []}
	bundle = detector.get_bundles().get(ac_unit)
	if bundle:
		out["model"] = {"n_rows": bundle["n_rows"], "trained_at": bundle.get("trained_at"), "pct": bundle.get("pct")}
		for feat in ml_per_ac.FEATURES:
			p = (bundle.get("profile") or {}).get(feat)
			if p:
				out["profile"].append({"name": action_guide.FRIENDLY.get(feat, feat), "unit": ml_per_ac.UNITS.get(feat, ""),
										"low": round(p["low"], 2), "mid": round(p["mid"], 2), "high": round(p["high"], 2)})
	conn = get_db_connection()
	try:
		try:
			out["learning"] = ml_per_ac.fetch_curve(conn, ac_unit)
		except Exception as e:
			conn.rollback()
			print(f"[ML] overview curve: {e}", flush=True)
		try:
			df = ml_per_ac.fetch_health(conn, ac_unit, days=30)
			if len(df):
				df["ts"] = ml_per_ac.pd.to_datetime(df["ts"], utc=True)
				last = df.iloc[-1]
				out["latest"] = {"t": last["ts"].isoformat(), "margin": float(last["margin"]), "flagged": bool(last["flagged"])}
				recent = df[df["ts"] >= df["ts"].max() - timedelta(days=3)]
				out["health"] = ml_per_ac.bucket_health(recent)
			out["trend"] = ml_per_ac.trend(df)
		except Exception as e:
			conn.rollback()
			print(f"[ML] overview health: {e}", flush=True)
		return out
	finally:
		conn.close()


@app.get("/api/ntfy/test")
def ntfy_test(request: Request):
	"""Open this URL while logged in to send a test notification to your phone."""
	if not get_admin_from_token(request.cookies.get("admin_session")):
		raise HTTPException(status_code=401, detail="Login required")
	return {"sent": ntfy_notifier.send_test(), "topic_configured": bool(os.environ.get("NTFY_TOPIC"))}
