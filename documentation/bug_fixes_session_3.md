# Bug Fixes and Diagnostics — Session 3

This document details the issues, fixes, and troubleshooting scripts implemented during this session to resolve ESP32 stability issues, verify sensor readings, and fix SMS dispatching bugs.

---

## 1. ESP32 Stability: Vibration Sensor (ADXL345) I2C Failure

### Problem
The ESP32 was crashing immediately on boot and entering a boot loop with the error:
`Exception: ADXL345 not detected! I2C scan: []`

Because the crash occurred in `SensorSystem.__init__`, the execution loop never reached `self.wifi.connect()`. This caused a total system failure and prevented the ESP32 from connecting to the Wi-Fi hotspot, even though the Wi-Fi credentials were correct.

### Fix — `sensor_system.py`
Modified the initialization and the read loop to gracefully handle the absence of the vibration sensor:

1. **Safe Initialization**: Wrapped the `VibrationSensor` instantiation in a `try...except` block. If the sensor fails the I2C scan, it logs a warning and sets `self.vibration = None` instead of crashing.
2. **Safe Read Fallback**: Inside the telemetry loop, we check if `self.vibration` is initialized. If not (or if reading fails), it defaults the vibration value to `0.0`.

```python
# __init__
try:
    self.vibration = VibrationSensor(sda_pin=21, scl_pin=22)
except Exception as e:
    print("Warning: ADXL345 Vibration Sensor failed to initialize. Falling back. Error:", e)
    self.vibration = None

# run loop
vibration_data = 0.0
if self.vibration is not None:
    try:
        vibration_data = self.vibration.read()
    except Exception as e:
        print("Error reading vibration sensor:", e)
        vibration_data = 0.0
```

---

## 2. SMS Alerts: Traccar Database Row Indexing Bug

### Problem
When the backend received an anomaly, the server failed to dispatch SMS alerts. 

The function `_get_enabled_numbers()` in `services/traccar_sms.py` query was structured as:
```python
cur.execute("SELECT ph_number FROM contacts WHERE enable = 1")
rows = cur.fetchall()
return [r[0] for r in rows]
```
However, the database connection is initialized with `psycopg2.extras.RealDictCursor`, meaning database rows are returned as **dictionaries** rather than tuples. Accessing `r[0]` threw a `KeyError: 0` and crashed the SMS dispatch pipeline.

### Fix — `services/traccar_sms.py`
Updated the list comprehension to use the dictionary key `"ph_number"`:
```python
# Before
return [r[0] for r in rows]

# After
return [r["ph_number"] for r in rows]
```

---

## 3. Added Diagnostics & Testing Scripts

To make system troubleshooting and verification easier, we added three specialized scripts:

### A. ESP32 Hardware Diagnostics (`esp32 code/test_sensors.py`)
A standalone test script for the ESP32 that runs locally on the board via Thonny.
* **Purpose**: Tests all physical sensors (Dust, DHT22, Vibration, Power Meter, DS18B20 Temp Probes) and logs their readings directly to the Thonny shell every 2 seconds.
* **Benefit**: Allows isolation of wiring or sensor hardware issues without needing a Wi-Fi connection or backend server.

### B. Live Telemetry Monitor (`AirBnBrrr/monitor_telemetry.py`)
A script running on the backend that connects to the Supabase PostgreSQL database.
* **Purpose**: Polls the `telemetry` table in real-time and prints out new incoming records formatted beautifully as they arrive.
* **Benefit**: Verifies that the ESP32 is successfully connected to the internet and successfully transmitting data to the backend.

### C. SMS Dispatch Verification (`AirBnBrrr/scratch/test_sms_sending.py`)
A verification script that executes the exact database lookup and HTTP POST requests used by the backend.
* **Purpose**: Verifies that the Traccar SMS Gateway API is reachable and responds with a `200 OK` when sending to enabled contacts.
