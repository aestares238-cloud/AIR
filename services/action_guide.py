"""
"What do I do now?" guide for AirBnBrrr alerts, in plain language.

Turns the rule-engine findings (and what the per-AC model found odd) into a short, ordered action
plan: how urgent it is, the first thing to do, what to check, and when to call a technician. The
plan is saved inside the alert (diagnoses -> action_plan), shown on the alert page, and the top
steps go in the ntfy notification.

No limit numbers are written here: the numbers come from the finding itself, which uses the limits
of that AC. General guidance for a window-type AC; electrical or refrigerant work needs a technician.
"""

URGENCY_ORDER = {"stop_now": 0, "today": 1, "soon": 2, "sensor": 3}
URGENCY_LABEL = {
    "stop_now": "Stop and check now",
    "today": "Check today",
    "soon": "Plan maintenance",
    "sensor": "Check the sensor",
}
SEVERITY_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

# Names a person understands instead of column names.
FRIENDLY = {
    "pzem_current": "current", "pzem_voltage": "voltage", "pzem_power": "power",
    "pzem_power_factor": "power factor", "pzem_frequency": "line frequency",
    "dht_temp": "output air temperature", "dht_humidity": "output humidity",
    "ds18b20_temp1": "outlet compressor temperature", "ds18b20_temp2": "inlet compressor temperature",
    "vibration": "compressor vibration",
}

# Problems that cover several readings at once: shown without a single number.
COMBINED = {"compressor_overheating", "reduced_cooling"}

WAIT = "Wait 5 minutes before turning it back on."

_CURRENT = dict(
    urgency="stop_now",
    short="Turn the AC off and unplug it. " + WAIT,
    do_now=["Turn the AC off and unplug it.", WAIT + " Then turn it on once and watch the current."],
    check=["Clean the outdoor part and check that its fan spins.", "Feel the plug and socket. If warm or burnt, stop using them.",
           "Check whether the voltage is also off."],
    call="the current is still too high, or the breaker trips.",
    why="The AC is working too hard. This can damage the compressor.",
)
_VOLTAGE = dict(
    urgency="today",
    short="If the voltage stays out of range, turn the AC off.",
    do_now=["If the voltage stays out of range for a few minutes, turn the AC off.", "Turn it on again only when the voltage is back to normal."],
    check=["Other big appliances on the same line.", "Loose wires at the main switch.", "Voltage regulator (AVR), if you have one."],
    call="the voltage keeps going out of range.",
    why="A bad power supply can damage the compressor.",
)
_NOT_RUNNING = dict(
    urgency="today",
    short="Check that the AC is on and set to cool. If you turned it off, ignore this.",
    do_now=["Check that the AC is on and set to cool.", "Listen for the compressor. If only the fan runs, the compressor is not starting."],
    check=["Power to the compressor.", "The start capacitor (a technician job)."],
    call="the fan runs but the compressor never starts.",
    why="The compressor may be off or not starting.",
)
_WARM_AIR = dict(
    urgency="today",
    short="Turn the AC off and clean the air filter, then restart it.",
    do_now=["Turn the AC off and clean the air filter.", "Restart and check that it cools within 15 minutes."],
    check=["Dirty indoor coil.", "Blocked air flow.", "Low refrigerant."],
    call="it is still too warm after cleaning.",
    why="The AC is not removing heat well.",
)
_OUTLET_HIGH = dict(
    urgency="stop_now",
    short="Check that the outdoor fan spins. Turn the AC off if it keeps rising.",
    do_now=["Check that the outdoor fan spins and nothing blocks the air.", "Turn the AC off if the current is also going up."],
    check=["Dirty outdoor coil.", "Fan motor.", "Hot air blowing back into the unit."],
    call="it goes over the limit again after cleaning.",
    why="The compressor is running too hot.",
)
_REFRIGERANT = dict(
    urgency="today",
    short="Turn the AC off if it is not cooling, and call a technician.",
    do_now=["Turn the AC off if it is not cooling.", "Look for oil stains or ice on the pipes."],
    check=["Refrigerant leak.", "Compressor."],
    call="the cooling stays weak. Refrigerant work needs a technician.",
    why="There may not be enough refrigerant.",
)
_FREEZING = dict(
    urgency="today",
    short="Turn the AC off for 30 minutes so any ice melts, then clean the filter.",
    do_now=["Turn the AC off for 30 minutes so any ice melts.", "Clean the filter and restart with a higher temperature setting."],
    check=["Ice on the indoor coil or pipes.", "Thermostat sensor."],
    call="it freezes up again.",
    why="The coil may be freezing.",
)


def _sensor(title, what, where):
    return dict(urgency="sensor", title=title, short=f"Check the {what} wires.", do_now=[f"Check the {what} wires and power."],
                check=[where], call="it stays offline after you re-seat the wires.", why="The sensor is not sending data.")


GUIDE = {
    "individual_current_high": dict(_CURRENT, title="Current is too high"),
    "compressor_overheating": dict(_CURRENT, title="Compressor is overloaded"),
    "individual_power_high": dict(_CURRENT, title="Power use is too high"),
    "high_voltage": dict(_VOLTAGE, title="Voltage is too high"),
    "low_voltage": dict(_VOLTAGE, title="Voltage is too low"),
    "individual_current_low": dict(_NOT_RUNNING, title="Current is too low"),
    "individual_power_low": dict(_NOT_RUNNING, title="Power use is too low"),
    "low_vibration": dict(_NOT_RUNNING, title="Compressor is not running"),
    "high_inlet_temp": dict(_WARM_AIR, title="Inlet compressor temperature is too high"),
    "individual_output_temp_high": dict(_WARM_AIR, title="Output air is too warm"),
    "high_outlet_temp": dict(_OUTLET_HIGH, title="Outlet compressor temperature is too high"),
    "reduced_cooling": dict(_REFRIGERANT, title="Cooling is weak"),
    "low_outlet_temp": dict(_REFRIGERANT, title="Outlet compressor temperature is too low"),
    "low_inlet_temp": dict(_FREEZING, title="Inlet compressor temperature is too low"),
    "individual_output_temp_low": dict(_FREEZING, title="Output air is too cold"),
    "excessive_vibration": dict(
        urgency="today", title="Compressor vibration is too high",
        short="Listen for rattling. Turn the AC off if it is loud.",
        do_now=["Listen for rattling or grinding.", "Turn the AC off if it is loud or getting worse."],
        check=["Loose compressor mounting.", "Outdoor fan blade.", "Worn bearings."],
        call="it keeps vibrating, or you hear grinding.", why="Something may be loose or worn."),
    "dht_humidity": dict(
        urgency="soon", title="Humidity is too high",
        short="Check that the water drain is not blocked.",
        do_now=["Check that the water drain is not blocked.", "Check that the indoor fan is running."],
        check=["Water dripping or pooling at the unit."], call="it stays high for days.", why="The air is not drying properly."),
    "dht_offline": _sensor("Temperature and humidity sensor is offline", "temperature and humidity sensor", "DHT22 on GPIO pin 18, power and ground."),
    "pzem_offline": _sensor("Power meter is offline", "power meter", "Serial wires to the ESP32. Switch the AC off at the breaker before touching mains wiring."),
    "temp1_offline": _sensor("Outlet temperature probe is offline", "outlet temperature probe", "DS18B20 probe on GPIO pin 33."),
    "temp2_offline": _sensor("Inlet temperature probe is offline", "inlet temperature probe", "DS18B20 probe on GPIO pin 25."),
    "vibration_offline": _sensor("Vibration sensor is offline", "vibration sensor", "ADXL345 I2C wires (SDA and SCL)."),
}

# What to look at when only the AI model flagged something (no rule fired).
FEATURE_HINTS = {
    "pzem_current": "Check the outdoor coil and fan, the plug, and the voltage.",
    "pzem_power": "Check the outdoor coil and fan.",
    "pzem_voltage": "Check the power supply and other big appliances on the line.",
    "pzem_power_factor": "A weak start capacitor or motor can cause this.",
    "pzem_frequency": "The power supply may be unstable.",
    "dht_temp": "Check the air filter and air flow.",
    "dht_humidity": "Check the water drain.",
    "ds18b20_temp1": "Check the outdoor coil and fan.",
    "ds18b20_temp2": "Check the indoor coil, filter and refrigerant.",
    "vibration": "Listen for rattling and check the compressor mounting.",
}


def short_name(issue):
    return (issue or "").split(" \u2014 ")[0].split(" - ")[0].strip()


def fmt_measured(f):
    """Measured value with its unit once (the rule engine often already includes the unit)."""
    val = str(f.get("measured_value", "")).strip()
    unit = (f.get("unit") or "").strip()
    if val and unit and unit not in val:
        val = f"{val} {unit}"
    return val


def plain_title(f):
    g = GUIDE.get(f.get("sensor_key"))
    return (g or {}).get("title") or short_name(f.get("issue"))


def plain_line(f):
    """One plain line for a finding, e.g. 'Current is too high: 12.5 A (normal ≤ 8.8 A)'."""
    title = plain_title(f)
    if f.get("sensor_key") in COMBINED:
        return title
    val = fmt_measured(f)
    if not val:
        return title
    normal = f.get("normal_range")
    return f"{title}: {val}" + (f" (normal {normal})" if normal else "")


def ml_features(ml):
    return [(n, z) for n, z in ((ml or {}).get("top_features") or [])]


def ml_names(ml):
    return [FRIENDLY.get(n, n) for n, _ in ml_features(ml)]


def ml_line(ml):
    """Short note for the AI model, with no jargon."""
    if not ml or not ml.get("is_anomaly"):
        return None
    names = ml_names(ml)
    return ("The AI also sees odd readings: " + ", ".join(names)) if names else "The AI sees this AC acting differently from its normal"


def _step_for(f):
    g = GUIDE.get(f.get("sensor_key"))
    urgency = g["urgency"] if g else ("stop_now" if f.get("severity") in ("High", "Critical") else "soon")
    do_now = list(g["do_now"]) if g else [f.get("recommended_action") or "Inspect the unit."]
    return {
        "id": f.get("sensor_key"),
        "title": plain_title(f),
        "severity": f.get("severity"),
        "urgency": urgency,
        "measured": "" if f.get("sensor_key") in COMBINED else fmt_measured(f),
        "normal": "" if f.get("sensor_key") in COMBINED else f.get("normal_range"),
        "short": (g or {}).get("short") or do_now[0],
        "why": (g or {}).get("why") or f.get("root_cause"),
        "do_now": do_now,
        "check": list((g or {}).get("check") or []),
        "call_technician_if": (g or {}).get("call"),
    }


def _sort_key(s):
    return (URGENCY_ORDER.get(s["urgency"], 9), -SEVERITY_RANK.get(s["severity"], 0))


def build_plan(findings, ml=None):
    """Ordered action plan: headline, the first things to do, and a step per problem."""
    steps, seen = [], set()
    for f in findings or []:
        if f.get("sensor_key") in seen:
            continue
        seen.add(f.get("sensor_key"))
        steps.append(_step_for(f))
    steps.sort(key=_sort_key)

    odd = ml_features(ml)
    ml_notes = [{"sensor": FRIENDLY.get(n, n), "hint": FEATURE_HINTS.get(n, "")} for n, _ in odd]
    if not steps and ml and ml.get("is_anomaly"):
        # only the AI model noticed something
        hints = [m["hint"] for m in ml_notes if m["hint"]][:2]
        steps.append({
            "id": "ai_model", "title": "This AC is acting differently from its normal", "severity": "Medium",
            "urgency": "today", "measured": "", "normal": "",
            "short": "Look at the AC: listen for new noises, feel the air, check the filter.",
            "why": "No limit was broken, but the readings no longer look like this AC's usual pattern.",
            "do_now": ["Look at the AC: listen for new noises, feel the air, check the filter."] + hints,
            "check": ["Compare today's readings with a normal day on the graphs."],
            "call_technician_if": "it keeps happening for a day or the cooling gets worse.",
        })

    top = steps[0]["urgency"] if steps else "today"
    first_steps = []
    for s in steps:
        line = f"{s['title']}: {s['short']}"
        if line not in first_steps:
            first_steps.append(line)
    return {
        "urgency": top,
        "headline": URGENCY_LABEL.get(top, "Check the AC"),
        "first_steps": first_steps[:3],
        "steps": steps,
        "ml_notes": ml_notes,
    }


def short_actions(findings, ml=None, n=2):
    """The most important things to do, one short line each (used in the ntfy notification)."""
    plan = build_plan(findings, ml)
    out = []
    for s in plan["steps"]:
        if s["short"] not in out:
            out.append(s["short"])
    return out[:n]


def _gsm(text):
    """SMS-friendly characters (a single special character would shrink every message segment)."""
    return (text.replace("\u2264", "<=").replace("\u2265", ">=").replace("\u00b0C", "C").replace("\u00b0", ""))


def sms_text(unit_title, is_critical, findings, ml=None):
    """Short plain SMS: urgency and AC name, the two worst problems, and the first thing to do."""
    ordered = sorted(findings or [], key=lambda f: -SEVERITY_RANK.get(f.get("severity"), 0))
    lines = [f"AirBnBrrr {'STOP' if is_critical else 'Check'}: {unit_title or 'AC'}"]
    lines += [f"- {plain_line(f)}" for f in ordered[:2]]
    if len(ordered) > 2:
        lines.append(f"+{len(ordered) - 2} more")
    if not ordered:
        lines.append("- " + (ml_line(ml) or "The AC is acting differently from its normal"))
    actions = short_actions(findings, ml, 1)
    if actions:
        lines.append("Do now: " + actions[0])
    return _gsm("\n".join(lines))
