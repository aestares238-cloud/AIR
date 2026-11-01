import ustruct
from micropython import const

# ADXL-345 registers
_DATA_FORMAT = const(0x31)
_POWER_CTL = const(0x2D)
_DATAX0 = const(0x32)


class ADXL345:
    def __init__(self, i2c, address=0x53):
        self.i2c = i2c
        self.address = address
        self.i2c.writeto_mem(self.address, _POWER_CTL, b"\x08")    # measurement on
        self.i2c.writeto_mem(self.address, _DATA_FORMAT, b"\x08")  # full resolution

    def read(self):
        # Always read from register 0x32 and decode as SIGNED 16-bit numbers.
        # (The old version did not select the register and treated negative values as huge positive ones.)
        data = self.i2c.readfrom_mem(self.address, _DATAX0, 6)
        x, y, z = ustruct.unpack("<hhh", data)
        return (x, y, z)
