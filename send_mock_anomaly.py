import os
import requests
import json

# Choose the target URL:
# - Use "https://YOUR-APP-NAME.onrender.com/telemetry" to send to your Render site (set TELEMETRY_API_KEY first if you use one).
# - Use "http://airbnbrrr.local:8000/telemetry" to send to the Raspberry Pi over the network.
# - Use "http://127.0.0.1:8000/telemetry" if running directly on the Raspberry Pi (or testing local server).
URL = "http://127.0.0.1:8000/telemetry"

# Create a payload with multiple severe anomalies
# This is guaranteed to trigger the anomaly model (if the unit has one) and multiple Rule Engine safety checks.
payload = {
    "dht_temp": 32.5,
    "dht_humidity": 78.0,
    "vibration": 125.0,             # > 100: Excessive Compressor Vibration
    "ds18b20_temp1": 96.5,         # > 90: High Discharge Temp (Compressor Heat)
    "ds18b20_temp2": 2.5,          # < 4.0: Evaporator Freezing (Cooling Pipe Temp)
    "pzem_voltage": 204.0,         # < 210: Undervoltage
    "pzem_current": 9.2,
    "pzem_power": 1950.0,          # > 1820: Overloaded Compressor / High Power Draw
    "pzem_energy": 1245.0,
    "pzem_frequency": 60.0,
    "pzem_power_factor": 0.72,     # < 0.85: Low Power Factor
}

print("Sending simulated anomaly payload to /telemetry...")
try:
    headers = {"X-API-Key": os.environ["TELEMETRY_API_KEY"]} if os.environ.get("TELEMETRY_API_KEY") else {}
    response = requests.post(URL, json=payload, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
    if response.status_code == 201:
        data = response.json()
        print("\nSUCCESS: Anomaly telemetry sent!")
        print(f"Stored Telemetry ID: {data.get('id')}")
        print("\nBecause process_anomaly runs in a FastAPI background task:")
        print("1. The database record is stored instantly.")
        print("2. The rule engine and AI analyses are being computed in the background.")
        print("3. Check your console log to verify when AI diagnostic and SMS processing are complete.")
        print("4. Go to your web dashboard Alerts page or visit the alert detail page directly once it is created.")
    else:
        print("\nERROR: Endpoint returned non-201 status.")
except Exception as e:
    print(f"\nConnection failed: {e}")
    print("Make sure your FastAPI server is running at http://127.0.0.1:8000")
