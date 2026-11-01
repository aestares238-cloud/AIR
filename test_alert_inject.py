# Standalone test script -- injects a simulated anomaly alert
# with BOTH rule_diagnoses and ai_diagnoses populated.
#
# Run from the project root:
#     venv\Scripts\python test_alert_inject.py
import sys
import json
import requests

# Force UTF-8 output so special chars don't crash on Windows console
sys.stdout.reconfigure(encoding='utf-8')

ALERT_URL = "http://127.0.0.1:8000/alerts"

# All values are deliberately out of spec to trigger every rule.
SIMULATED = {
    "dht_temp":           28.5,
    "dht_humidity":       72.0,
    "vibration":          125.0,   # > 100 -> excessive vibration
    "ds18b20_temp1":      96.3,    # > 90C -> high discharge temp
    "ds18b20_temp2":      2.1,     # < 4C  -> evaporator freezing
    "pzem_voltage":       207.4,   # < 210V -> undervoltage
    "pzem_current":       9.2,
    "pzem_power":         1950.0,  # > 1820W -> compressor overload
    "pzem_energy":        1.24,
    "pzem_frequency":     60.1,    # within range -> PASS
    "pzem_power_factor":  0.71,    # < 0.85 -> capacitor degradation
}

# Run the rule engine
from services.rule_engine import analyze_with_rules
rule_result = analyze_with_rules(SIMULATED)

print("=== RULE ENGINE RESULT ===")
print(f"Overall Severity : {rule_result['overall_severity']}")
print(f"Sensors Checked  : {rule_result['sensors_checked']}")
print(f"Rules Triggered  : {rule_result['sensors_triggered']}")
print()
for step in rule_result["computation_steps"]:
    verdict = step["result"]
    icon    = "X " if verdict == "TRIGGERED" else ("OK" if verdict == "PASS" else "--")
    expr    = step.get("expression") or step.get("reason", "")
    sensor  = step["sensor"][:34]
    value   = step["value"][:19]
    print(f"  [{icon}] [{verdict:9}] {sensor:34} | {value:19} | {expr}")

print()

# Simulated AI diagnoses (mocked since no live API in this test)
ai_diagnoses = {
    "diagnoses": [
        {
            "issue": "Simultaneous Compressor Overload and Evaporator Freeze-Up",
            "status": "Current",
            "confidence_score": 96,
            "root_cause": (
                "Power draw of 651.2 W exceeds rated max (600 W) while the suction line "
                "is frozen at 2.1 C. High power with freezing suction strongly suggests "
                "a failing run capacitor forcing the compressor to overwork while restricted "
                "airflow causes the evaporator to ice up."
            ),
            "severity": "Critical",
            "recommended_action": (
                "Shut down the unit immediately. Clean the air filter. "
                "Test and replace the run capacitor. Have refrigerant pressure "
                "verified before restarting."
            ),
        },
        {
            "issue": "Imminent Condenser Coil Failure from Sustained Overheating",
            "status": "Predicted",
            "confidence_score": 88,
            "root_cause": (
                "Discharge temp at 96.3 C with power at 651.2 W indicates heat "
                "is not being rejected efficiently. Sustained operation above 90 C "
                "will degrade compressor valve assemblies within days."
            ),
            "severity": "High",
            "recommended_action": (
                "Clean condenser fins thoroughly. Ensure adequate clearance around "
                "the outdoor side of the unit. Do not operate until discharge temp "
                "is confirmed below 85 C."
            ),
        },
    ]
}

# Combine both layers
combined_diagnoses = json.dumps({
    "rule_diagnoses": rule_result,
    "ai_diagnoses":   ai_diagnoses,
})

# Build summary from rule findings
findings = rule_result["findings"]
high     = [f for f in findings if f["severity"] in ("High", "Critical")]
lines    = ["[RULE ENGINE] !! AC Diagnostic Alert !!"]
for f in high[:2]:
    parts = [p.strip() for p in f["recommended_action"].split(". ") if p.strip()]
    if parts:
        if parts[0].isdigit() and len(parts) > 1:
            action_short = f"{parts[0]}. {parts[1]}."
        else:
            action_short = f"{parts[0]}."
    else:
        action_short = "Inspect unit."
    lines.append(f"\n[{f['severity'].upper()}] {f['issue']}\nAction: {action_short}")
lines.append("\n\nCheck full system report for details.")
summary = "\n".join(lines)

# POST to the running server
payload = {"summary": summary, "diagnoses": combined_diagnoses}
print("=== POSTING ALERT ===")
resp = requests.post(ALERT_URL, json=payload)
if resp.ok:
    data = resp.json()
    print(f"[OK] Alert created! ID: {data['id']}")
    print(f"     View at: http://127.0.0.1:8000/pages/alert?id={data['id']}")
else:
    print(f"[FAIL] {resp.status_code} -- {resp.text}")
