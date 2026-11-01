# ESP32 settings: edit this file, keep the other files as they are.
WIFI_SSID = "YOUR_WIFI_NAME"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# Your Render address (https), not the Pi. The ESP32 only needs internet now, on any WiFi.
SERVER_URL = "https://YOUR-APP-NAME.onrender.com/telemetry"

# Must be the same text as the TELEMETRY_API_KEY setting on Render.
API_KEY = "PUT-A-LONG-RANDOM-TEXT-HERE"

# Which AC this ESP32 measures: the device code shown on the Manage ACs page.
AC_UNIT = "AC1"

INTERVAL_S = 10          # seconds between readings
USE_WATCHDOG = True      # reboots the ESP32 if it hangs (set False while you debug in Thonny)
