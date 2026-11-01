from machine import Pin
import dht


class DHTSensor:
    def __init__(self, pin):
        self.sensor = dht.DHT22(Pin(pin))

    def read(self):
        """Returns temperature and humidity, or None for both when the sensor does not answer."""
        try:
            self.sensor.measure()
            return {"temperature": self.sensor.temperature(), "humidity": self.sensor.humidity()}
        except Exception as e:
            print("DHT22 error:", e)
            return {"temperature": None, "humidity": None}
