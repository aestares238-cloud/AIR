"""
Rule-Based Anomaly Detection Engine for AirBnBrrr
=================================================
A deterministic safety check:
1. Handles sensor offline/disconnected states (None values).
2. Combined checks (Compressor Overheating, Reduced Cooling).
3. Individual sensor checks, only when the reading is not None.

The numbers are the per-AC limits (services/limits.py), editable on the Manage ACs page.
analyze_with_rules(telemetry, limits) uses the limits it is given; with no limits it uses the
defaults, which are the original 1.5 HP window AC values. The dust sensor is no longer used.
"""
import re

from services.limits import merged

_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])")


def _fmt_like(token, new):
    text = f"{new:g}"
    return text + ".0" if ("." in token and "." not in text) else text


def _retext(text, pairs):
    """Put the AC's own limits into the explanation texts (default numbers are swapped for the new ones)."""
    if not isinstance(text, str):
        return text

    def sub(m):
        token = m.group(1)
        for old, new in pairs:
            if float(token) == float(old):
                return token if float(new) == float(old) else _fmt_like(token, new)
        return token

    return _NUM.sub(sub, text)


def _num(tel, field):
    v = tel.get(field)
    return None if v is None else float(v)


def _above(field, bound, guard=None, inclusive=False):
    def check(tel, L):
        v = _num(tel, field)
        if v is None:
            return False
        if not (v >= bound(L) if inclusive else v > bound(L)):
            return False
        return not (guard is not None and guard(tel, L))
    return check


def _below(field, bound, guard=None):
    def check(tel, L):
        v = _num(tel, field)
        if v is None or not v < bound(L):
            return False
        return not (guard is not None and guard(tel, L))
    return check


def is_overheating(tel, L):
    try:
        return (
            tel.get("pzem_current") is not None and float(tel.get("pzem_current")) >= L["current"]["max"] and
            tel.get("pzem_power") is not None and float(tel.get("pzem_power")) >= L["power"]["max"] and
            tel.get("vibration") is not None and float(tel.get("vibration")) >= L["vibration"]["max"]
        )
    except Exception:
        return False


def is_reduced_cooling(tel, L):
    try:
        return (
            tel.get("ds18b20_temp1") is not None and float(tel.get("ds18b20_temp1")) >= L["outlet_temp"]["max"] and
            tel.get("dht_temp") is not None and float(tel.get("dht_temp")) >= L["output_temp"]["max"] - 4 and
            tel.get("ds18b20_temp2") is not None and float(tel.get("ds18b20_temp2")) >= L["inlet_temp"]["max"] + 5
        )
    except Exception:
        return False


# Each rule: the text as written for the default limits, the check, and which default numbers in the
# text belong to which limit (so the explanation follows the AC's own limits).
_BASE_RULES = [
    {
        'id': 'dht_offline',
        'label': 'DHT Sensor Offline',
        'description': 'Checks if output air temperature or humidity is missing/null',
        'issue': 'DHT Sensor Offline',
        'severity': 'High',
        'root_cause': 'The output air temperature or humidity reading is missing, indicating the DHT22 sensor is not communicating with the ESP32.',
        'recommended_action': 'Check physical wiring of the DHT22 sensor to GPIO Pin 18 and verify VCC/GND power.',
        'normal_range': 'Valid reading (non-null)',
        'measured_val_func': lambda tel: f"Temp: {tel.get('dht_temp')}°C, Hum: {tel.get('dht_humidity')}%",
        'unit': '',
        'check': lambda tel, L: tel.get("dht_temp") is None or tel.get("dht_humidity") is None,
        'limits': [],
    },
    {
        'id': 'pzem_offline',
        'label': 'Power Meter Offline',
        'description': 'Checks if PZEM power meter readings are missing/null',
        'issue': 'Power Meter Offline',
        'severity': 'High',
        'root_cause': 'PZEM-004T power meter readings are missing, indicating serial UART communication loss.',
        'recommended_action': 'Verify PZEM-004T serial UART connection and power supply.',
        'normal_range': 'Valid reading (non-null)',
        'measured_val_func': lambda tel: f"Voltage: {tel.get('pzem_voltage')}V, Current: {tel.get('pzem_current')}A",
        'unit': '',
        'check': lambda tel, L: tel.get("pzem_voltage") is None or tel.get("pzem_current") is None,
        'limits': [],
    },
    {
        'id': 'temp1_offline',
        'label': 'Outlet Temp Probe Offline',
        'description': 'Checks if DS18B20 outlet temperature probe is missing/null',
        'issue': 'Outlet Temp Probe Offline',
        'severity': 'High',
        'root_cause': 'The DS18B20 outlet compressor temperature probe returned no data.',
        'recommended_action': 'Check DS18B20 outlet temperature probe wire connection to GPIO Pin 33.',
        'normal_range': 'Valid reading (non-null)',
        'measured_val_func': lambda tel: f"Outlet: {tel.get('ds18b20_temp1')}°C",
        'unit': '',
        'check': lambda tel, L: tel.get("ds18b20_temp1") is None,
        'limits': [],
    },
    {
        'id': 'temp2_offline',
        'label': 'Inlet Temp Probe Offline',
        'description': 'Checks if DS18B20 inlet temperature probe is missing/null',
        'issue': 'Inlet Temp Probe Offline',
        'severity': 'High',
        'root_cause': 'The DS18B20 inlet compressor temperature probe returned no data.',
        'recommended_action': 'Check DS18B20 inlet temperature probe wire connection to GPIO Pin 25.',
        'normal_range': 'Valid reading (non-null)',
        'measured_val_func': lambda tel: f"Inlet: {tel.get('ds18b20_temp2')}°C",
        'unit': '',
        'check': lambda tel, L: tel.get("ds18b20_temp2") is None,
        'limits': [],
    },
    {
        'id': 'vibration_offline',
        'label': 'Vibration Sensor Offline',
        'description': 'Checks if vibration sensor reading is missing/null',
        'issue': 'Vibration Sensor Offline',
        'severity': 'Medium',
        'root_cause': 'The ADXL345 vibration sensor I2C communication is offline.',
        'recommended_action': 'Check ADXL345 I2C connections (SDA/SCL) and verify pull-up resistors.',
        'normal_range': 'Valid reading (non-null)',
        'measured_val_func': lambda tel: f"Vib: {tel.get('vibration')} Hz",
        'unit': '',
        'check': lambda tel, L: tel.get("vibration") is None,
        'limits': [],
    },
    {
        'id': 'compressor_overheating',
        'label': 'Compressor Overheating',
        'description': 'Deterministic safety check: Current >= 8.8 A AND Power >= 1860 W AND Vibration >= 90 Hz',
        'issue': 'Compressor Overheating',
        'severity': 'High',
        'root_cause': 'Indicates the compressor is under high electrical and mechanical load, commonly associated with reduced condenser cooling efficiency or compressor overloading.',
        'recommended_action': 'Check whether the condenser fan is operating properly. Stop operating the air conditioner if the current continues to increase to prevent compressor damage and protect the electrical wiring and circuit breaker.',
        'normal_range': 'Current < 8.8 A OR Power < 1860 W OR Vibration < 90 Hz',
        'measured_val_func': lambda tel: f"Current: {tel.get('pzem_current')} A, Power: {tel.get('pzem_power')} W, Vibration: {tel.get('vibration')} Hz",
        'unit': '',
        'check': is_overheating,
        'limits': [(8.8, lambda L: L["current"]["max"]), (1860, lambda L: L["power"]["max"]), (90, lambda L: L["vibration"]["max"])],
    },
    {
        'id': 'reduced_cooling',
        'label': 'Reduced Cooling Performance',
        'description': 'Deterministic check: Outlet Compressor >= 61°C AND Output Air >= 21°C AND Inlet >= 22°C',
        'issue': 'Reduced Cooling Performance',
        'severity': 'Medium',
        'root_cause': 'The monitored temperatures indicate a reduction in cooling performance. Inspect the refrigerant system for possible refrigerant leakage or insufficient refrigerant charge.',
        'recommended_action': 'The monitored temperatures indicate a reduction in cooling performance. Inspect the refrigerant system for possible refrigerant leakage or insufficient refrigerant charge. Verify the condition using appropriate refrigeration service equipment and perform corrective maintenance if necessary.',
        'normal_range': 'Outlet < 61°C OR Output < 21°C OR Inlet < 22°C',
        'measured_val_func': lambda tel: f"Outlet: {tel.get('ds18b20_temp1')}°C, Output: {tel.get('dht_temp')}°C, Inlet: {tel.get('ds18b20_temp2')}°C",
        'unit': '°C',
        'check': is_reduced_cooling,
        'limits': [(61, lambda L: L["outlet_temp"]["max"]), (21, lambda L: L["output_temp"]["max"] - 4), (22, lambda L: L["inlet_temp"]["max"] + 5)],
    },
    {
        'id': 'high_voltage',
        'label': 'High Voltage Supply',
        'description': 'Voltage supply check (> 241 V)',
        'issue': 'High Voltage - Overvoltage supply',
        'severity': 'High',
        'root_cause': 'Voltage supply exceeds the safe operating limit of 241 V.',
        'recommended_action': 'Verify input voltage stability and check voltage regulator status.',
        'normal_range': '≤ 241 V',
        'measured_val_func': lambda tel: f"{tel.get('pzem_voltage')} V",
        'unit': 'V',
        'check': _above("pzem_voltage", lambda L: L["voltage"]["max"]),
        'limits': [(241, lambda L: L["voltage"]["max"])],
    },
    {
        'id': 'low_voltage',
        'label': 'Low Voltage Supply',
        'description': 'Voltage supply check (< 225 V)',
        'issue': 'Low Voltage - Undervoltage supply',
        'severity': 'High',
        'root_cause': 'Voltage supply is below the safe operating limit of 225 V.',
        'recommended_action': 'Verify input voltage stability and check voltage regulator status.',
        'normal_range': '≥ 225 V',
        'measured_val_func': lambda tel: f"{tel.get('pzem_voltage')} V",
        'unit': 'V',
        'check': _below("pzem_voltage", lambda L: L["voltage"]["min"]),
        'limits': [(225, lambda L: L["voltage"]["min"])],
    },
    {
        'id': 'high_inlet_temp',
        'label': 'High Inlet Temperature',
        'description': 'Inlet compressor suction temp check (> 17 °C)',
        'issue': 'High Inlet Temperature (Suction) — Dirty evaporator coil',
        'severity': 'High',
        'root_cause': 'Inlet compressor suction line temperature is above the safe operating limit of 17 °C.',
        'recommended_action': 'Inspect suction line insulation, check expansion valve operation, and verify refrigerant charge.',
        'normal_range': '≤ 17.0 °C',
        'measured_val_func': lambda tel: f"{tel.get('ds18b20_temp2')} °C",
        'unit': '°C',
        'check': _above("ds18b20_temp2", lambda L: L["inlet_temp"]["max"], guard=is_reduced_cooling),
        'limits': [(17, lambda L: L["inlet_temp"]["max"])],
    },
    {
        'id': 'low_inlet_temp',
        'label': 'Low Inlet Temperature',
        'description': 'Inlet compressor suction temp check (< 8 °C)',
        'issue': 'Low Inlet Temperature (Suction) — faulty thermostat',
        'severity': 'High',
        'root_cause': 'Inlet compressor suction line temperature is below the safe operating limit of 8 °C.',
        'recommended_action': 'Inspect suction line insulation, check expansion valve operation, and verify refrigerant charge.',
        'normal_range': '≥ 8.0 °C',
        'measured_val_func': lambda tel: f"{tel.get('ds18b20_temp2')} °C",
        'unit': '°C',
        'check': _below("ds18b20_temp2", lambda L: L["inlet_temp"]["min"], guard=is_reduced_cooling),
        'limits': [(8, lambda L: L["inlet_temp"]["min"])],
    },
    {
        'id': 'high_outlet_temp',
        'label': 'High Outlet Compressor Temp',
        'description': 'Outlet compressor discharge temp check (> 61 °C)',
        'issue': 'High Outlet Temperature (Discharge) — Dirty condenser coil',
        'severity': 'High',
        'root_cause': 'Outlet compressor discharge line temperature is above the safe operating limit of 61 °C.',
        'recommended_action': 'Check whether the condenser fan is operating properly. Stop operating the air conditioner if the current continues to increase to prevent compressor damage and protect the electrical wiring and circuit breaker.',
        'normal_range': '≤ 61.0 °C',
        'measured_val_func': lambda tel: f"{tel.get('ds18b20_temp1')} °C",
        'unit': '°C',
        'check': _above("ds18b20_temp1", lambda L: L["outlet_temp"]["max"], guard=is_reduced_cooling),
        'limits': [(61, lambda L: L["outlet_temp"]["max"])],
    },
    {
        'id': 'low_outlet_temp',
        'label': 'Low Outlet Compressor Temp',
        'description': 'Outlet compressor discharge temp check (< 50 °C)',
        'issue': 'Low Outlet Temperature (Discharge) — Low refrigerant charge',
        'severity': 'High',
        'root_cause': 'Outlet compressor discharge line temperature is below the safe operating limit of 50 °C.',
        'recommended_action': 'Check compressor operation and verify system refrigerant level.',
        'normal_range': '≥ 50.0 °C',
        'measured_val_func': lambda tel: f"{tel.get('ds18b20_temp1')} °C",
        'unit': '°C',
        'check': _below("ds18b20_temp1", lambda L: L["outlet_temp"]["min"], guard=is_reduced_cooling),
        'limits': [(50, lambda L: L["outlet_temp"]["min"])],
    },
    {
        'id': 'low_vibration',
        'label': 'Low Vibration',
        'description': 'Compressor low vibration check (< 10 Hz)',
        'issue': 'Low Vibration — Compressor not operating, fan not running or off',
        'severity': 'High',
        'root_cause': 'Vibration frequency is abnormally low, suggesting the unit is not running or operating.',
        'recommended_action': 'Verify power supply to compressor and fan; check starter capacitors and contactors.',
        'normal_range': '≥ 10 Hz',
        'measured_val_func': lambda tel: f"{tel.get('vibration')} Hz",
        'unit': 'Hz',
        'check': _below("vibration", lambda L: L["vibration"]["min"]),
        'limits': [(10, lambda L: L["vibration"]["min"])],
    },
    {
        'id': 'excessive_vibration',
        'label': 'Excessive Vibration',
        'description': 'Compressor excessive vibration check (>= 90 Hz)',
        'issue': 'Excessive Vibration — Loose compressor mounting, worn bearings, condenser fan imbalance',
        'severity': 'Medium',
        'root_cause': 'Vibration frequency exceeds the safety threshold of 90 Hz.',
        'recommended_action': 'Inspect the compressor mounting, internal components, and check for signs of compressor wear or mechanical looseness.',
        'normal_range': '< 90 Hz',
        'measured_val_func': lambda tel: f"{tel.get('vibration')} Hz",
        'unit': 'Hz',
        'check': _above("vibration", lambda L: L["vibration"]["max"], guard=is_overheating, inclusive=True),
        'limits': [(90, lambda L: L["vibration"]["max"])],
    },
    {
        'id': 'individual_current_low',
        'label': 'Low Current Draw',
        'description': 'Current draw check (< 7.6 A)',
        'issue': 'Low Current Anomaly',
        'severity': 'High',
        'root_cause': 'Current draw is below the normal operating limit of 7.6 A.',
        'recommended_action': 'Inspect electrical wiring and check compressor loading.',
        'normal_range': '≥ 7.6 A',
        'measured_val_func': lambda tel: f"{tel.get('pzem_current')} A",
        'unit': 'A',
        'check': _below("pzem_current", lambda L: L["current"]["min"]),
        'limits': [(7.6, lambda L: L["current"]["min"])],
    },
    {
        'id': 'individual_current_high',
        'label': 'High Current Draw',
        'description': 'Current draw check (> 8.8 A)',
        'issue': 'High Current Anomaly',
        'severity': 'High',
        'root_cause': 'Current draw is above the normal operating limit of 8.8 A.',
        'recommended_action': 'Inspect electrical wiring, connections, and check compressor motor draws.',
        'normal_range': '≤ 8.8 A',
        'measured_val_func': lambda tel: f"{tel.get('pzem_current')} A",
        'unit': 'A',
        'check': _above("pzem_current", lambda L: L["current"]["max"], guard=is_overheating),
        'limits': [(8.8, lambda L: L["current"]["max"])],
    },
    {
        'id': 'individual_power_low',
        'label': 'Low Power Consumption',
        'description': 'Power draw check (< 1650 W)',
        'issue': 'Low Power Anomaly',
        'severity': 'High',
        'root_cause': 'Power draw is below the normal operating limit of 1650 W.',
        'recommended_action': 'Check line voltage stability and compressor capacitors.',
        'normal_range': '≥ 1650 W',
        'measured_val_func': lambda tel: f"{tel.get('pzem_power')} W",
        'unit': 'W',
        'check': _below("pzem_power", lambda L: L["power"]["min"]),
        'limits': [(1650, lambda L: L["power"]["min"])],
    },
    {
        'id': 'individual_power_high',
        'label': 'High Power Consumption',
        'description': 'Power draw check (> 1860 W)',
        'issue': 'High Power Anomaly',
        'severity': 'High',
        'root_cause': 'Power draw is above the normal operating limit of 1860 W.',
        'recommended_action': 'Check compressor electrical loading and verify line stability.',
        'normal_range': '≤ 1860 W',
        'measured_val_func': lambda tel: f"{tel.get('pzem_power')} W",
        'unit': 'W',
        'check': _above("pzem_power", lambda L: L["power"]["max"], guard=is_overheating),
        'limits': [(1860, lambda L: L["power"]["max"])],
    },
    {
        'id': 'individual_output_temp_low',
        'label': 'Low Output Temp',
        'description': 'Supply air output temp check (< 7 °C)',
        'issue': 'Low Output Temp Anomaly',
        'severity': 'High',
        'root_cause': 'Supply air output temperature is below the safe limit of 7 °C.',
        'recommended_action': 'Inspect evaporator for frost buildup, verify fan operation.',
        'normal_range': '≥ 7.0 °C',
        'measured_val_func': lambda tel: f"{tel.get('dht_temp')} °C",
        'unit': '°C',
        'check': _below("dht_temp", lambda L: L["output_temp"]["min"], guard=is_reduced_cooling),
        'limits': [(7, lambda L: L["output_temp"]["min"])],
    },
    {
        'id': 'individual_output_temp_high',
        'label': 'High Output Temp',
        'description': 'Supply air output temp check (> 25 °C)',
        'issue': 'High Output Temp Anomaly',
        'severity': 'High',
        'root_cause': 'Supply air output temperature is above the safe limit of 25 °C.',
        'recommended_action': 'Inspect evaporator fan, clean filter, and check for correct air discharge.',
        'normal_range': '≤ 25.0 °C',
        'measured_val_func': lambda tel: f"{tel.get('dht_temp')} °C",
        'unit': '°C',
        'check': _above("dht_temp", lambda L: L["output_temp"]["max"], guard=is_reduced_cooling),
        'limits': [(25, lambda L: L["output_temp"]["max"])],
    },
    {
        'id': 'dht_humidity',
        'label': 'Humidity',
        'description': 'Relative humidity check (<= 80%)',
        'issue': 'Humidity Anomaly',
        'severity': 'Low',
        'root_cause': 'Relative humidity exceeds the normal operating limit of 80%.',
        'recommended_action': 'Verify indoor fan speeds, check return air humidity, and confirm condensate drainage.',
        'normal_range': '≤ 80 %',
        'measured_val_func': lambda tel: f"{tel.get('dht_humidity')} %",
        'unit': '%',
        'check': _above("dht_humidity", lambda L: L["humidity"]["max"]),
        'limits': [(80, lambda L: L["humidity"]["max"])],
    },
]


def build_rules(L):
    """The rules with the numbers of one AC's limits."""
    rules = []
    for base in _BASE_RULES:
        pairs = [(old, getter(L)) for old, getter in base["limits"]]
        rule = {k: (_retext(v, pairs) if isinstance(v, str) else v) for k, v in base.items() if k not in ("limits", "check", "measured_val_func")}
        rule["measured_val_func"] = base["measured_val_func"]
        rule["check"] = (lambda tel, _c=base["check"]: _c(tel, L))
        rules.append(rule)
    return rules


def analyze_with_rules(telemetry: dict, limits: dict = None) -> dict:
    L = merged(limits)
    findings = []
    computation_steps = []
    severity_rank = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    overall_severity = None
    sensors_checked = 0
    sensors_triggered = 0

    for rule in build_rules(L):
        sensors_checked += 1
        triggered = False
        try:
            triggered = rule["check"](telemetry)
        except Exception:
            pass

        measured_val = rule["measured_val_func"](telemetry)

        if triggered:
            finding = {
                "sensor":              rule["label"],
                "sensor_key":          rule["id"],
                "measured_value":      measured_val,
                "unit":                rule["unit"],
                "normal_range":        rule["normal_range"],
                "computed_expression": f"Triggered: {measured_val}",
                "issue":               rule["issue"],
                "severity":            rule["severity"],
                "status":              "Current",
                "root_cause":          rule["root_cause"],
                "recommended_action":  rule["recommended_action"],
            }
            findings.append(finding)

            rank = severity_rank.get(rule["severity"], 0)
            if overall_severity is None or rank > severity_rank.get(overall_severity, 0):
                overall_severity = rule["severity"]

            computation_steps.append({
                "sensor":       rule["label"],
                "value":        measured_val,
                "normal_range": rule["normal_range"],
                "result":       "TRIGGERED",
                "expression":   f"Value {measured_val} triggers threshold",
                "severity":     rule["severity"],
                "issue":        rule["issue"],
            })
            sensors_triggered += 1
        else:
            computation_steps.append({
                "sensor":       rule["label"],
                "value":        measured_val,
                "normal_range": rule["normal_range"],
                "result":       "PASS",
                "reason":       "Value within normal operating range",
            })

    return {
        "findings":          findings,
        "overall_severity":  overall_severity or "Normal",
        "sensors_checked":   sensors_checked,
        "sensors_triggered": sensors_triggered,
        "computation_steps": computation_steps,
    }
