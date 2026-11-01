from machine import Pin
import onewire
import ds18x20


class TemperatureProbe:
    """DS18B20. Call start() on every probe first, wait about 800 ms once, then read() each one."""

    def __init__(self, pin):
        self.ow = onewire.OneWire(Pin(pin))
        self.ds = ds18x20.DS18X20(self.ow)
        self.roms = []

    def start(self):
        try:
            if not self.roms:
                self.roms = self.ds.scan()
            if self.roms:
                self.ds.convert_temp()
        except Exception as e:
            print("DS18B20 start error:", e)
            self.roms = []

    def read(self):
        try:
            if not self.roms:
                return None
            return self.ds.read_temp(self.roms[0])
        except Exception as e:
            print("DS18B20 read error:", e)
            self.roms = []
            return None
