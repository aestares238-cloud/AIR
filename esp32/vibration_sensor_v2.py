from machine import Pin, SoftI2C
import math
from adxl345 import ADXL345


class VibrationSensor:
    def __init__(self, sda_pin=21, scl_pin=22):
        self.i2c = SoftI2C(scl=Pin(scl_pin), sda=Pin(sda_pin))
        devices = self.i2c.scan()
        if not devices:
            raise Exception("ADXL345 not detected! I2C scan: []")
        self.accel = ADXL345(self.i2c)
        self.prev_mag = None

    def read(self):
        # Same measure as before: how much the total acceleration changed since the last reading.
        x, y, z = self.accel.read()
        mag = math.sqrt(x * x + y * y + z * z)
        if self.prev_mag is None:
            self.prev_mag = mag
            return 0
        vibration = abs(mag - self.prev_mag)
        self.prev_mag = mag
        return vibration
