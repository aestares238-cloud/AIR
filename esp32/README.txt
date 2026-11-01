ESP32 sketch (MicroPython) for AirBnBrrr: posts every reading straight to the Render website.

Upload ALL of these files to the ESP32 (Thonny: right-click -> "Upload to /"):
  boot.py  main.py  config.py  sensor_system.py  api_client.py  wifi_manager.py
  dht_sensor_v2.py  vibration_sensor_v2.py  adxl345.py  power_meter_v2.py  temp_probe_sensor_v2.py
plus your existing pzem004t.py (unchanged, it is not in this folder).
The dust sensor files are no longer needed: delete dust_sensor_v2.py from the ESP32.

Before uploading, edit config.py: WiFi name and password, SERVER_URL, API_KEY, AC_UNIT.
On Render add the setting TELEMETRY_API_KEY with the SAME text as API_KEY.
