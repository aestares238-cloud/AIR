import network
import time


class WiFiManager:
    def __init__(self, ssid, password):
        self.ssid = ssid
        self.password = password
        self.wlan = network.WLAN(network.STA_IF)

    def connect(self, timeout=20):
        """Connect if needed. Returns True when online. Safe to call every loop (it reconnects after a drop)."""
        self.wlan.active(True)
        if self.wlan.isconnected():
            return True
        try:
            self.wlan.disconnect()
        except Exception:
            pass
        self.wlan.connect(self.ssid, self.password)
        start = time.time()
        while not self.wlan.isconnected() and time.time() - start < timeout:
            time.sleep(0.5)
        if self.wlan.isconnected():
            print("WiFi connected:", self.wlan.ifconfig())
            return True
        print("WiFi not connected, will try again")
        return False
