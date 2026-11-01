from dht_sensor_v2 import DHTSensor
from vibration_sensor_v2 import VibrationSensor
from power_meter_v2 import PowerMeter
from temp_probe_sensor_v2 import TemperatureProbe
from api_client import APIClient
from wifi_manager import WiFiManager
import config
import time


class SensorSystem:
    def __init__(self):
        self.dht = DHTSensor(18)
        try:
            self.vibration = VibrationSensor(sda_pin=21, scl_pin=22)
        except Exception as e:
            print("Warning: ADXL345 vibration sensor failed to start:", e)
            self.vibration = None

        self.power = PowerMeter()
        self.temp1 = TemperatureProbe(33)   # outlet compressor
        self.temp2 = TemperatureProbe(25)   # inlet compressor

        self.api = APIClient(config.SERVER_URL, config.API_KEY)
        self.wifi = WiFiManager(config.WIFI_SSID, config.WIFI_PASSWORD)

    @staticmethod
    def _safe(fn, default=None):
        """One broken sensor must never stop the whole program: it just reports None (= offline)."""
        try:
            return fn()
        except Exception as e:
            print("Sensor error:", e)
            return default

    def read_all(self):
        t0 = time.ticks_ms()
        # start both temperature probes first, read the other sensors while they measure
        self.temp1.start()
        self.temp2.start()
        dht_data = self._safe(self.dht.read, None) or {}
        power_data = self._safe(self.power.read, None) or {}
        vibration = self._safe(self.vibration.read, None) if self.vibration is not None else None

        wait = 800 - time.ticks_diff(time.ticks_ms(), t0)   # the probes need about 750 ms
        if wait > 0:
            time.sleep_ms(wait)

        return {
            "ac_unit": config.AC_UNIT,
            "dht_temp": dht_data.get("temperature"),
            "dht_humidity": dht_data.get("humidity"),
            "vibration": vibration,
            "ds18b20_temp1": self._safe(self.temp1.read, None),
            "ds18b20_temp2": self._safe(self.temp2.read, None),
            "pzem_voltage": power_data.get("voltage"),
            "pzem_current": power_data.get("current"),
            "pzem_power": power_data.get("power"),
            "pzem_energy": power_data.get("energy"),
            "pzem_frequency": power_data.get("frequency"),
            "pzem_power_factor": power_data.get("power_factor"),
        }

    def run(self):
        wdt = None
        if config.USE_WATCHDOG:
            from machine import WDT
            wdt = WDT(timeout=120000)       # reboots if something hangs for 2 minutes

        self.wifi.connect()
        while True:
            start = time.ticks_ms()
            if wdt:
                wdt.feed()

            payload = self.read_all()
            print(payload)
            if wdt:
                wdt.feed()

            if self.wifi.connect():         # reconnects by itself after a WiFi drop
                self.api.send(payload)
            if wdt:
                wdt.feed()

            # keep a steady rhythm: INTERVAL_S from the START of this round
            used = time.ticks_diff(time.ticks_ms(), start)
            time.sleep_ms(max(0, config.INTERVAL_S * 1000 - used))
