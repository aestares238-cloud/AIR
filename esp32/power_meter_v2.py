from pzem004t import PZEM
from machine import UART


class PowerMeter:
    def __init__(self, uart_id=2, tx=17, rx=16, set_address=False):
        self.uart = UART(uart_id, baudrate=9600, tx=tx, rx=rx)
        self.dev = PZEM(uart=self.uart)
        if set_address:                 # only needed once, on a brand new PZEM
            self.dev.setAddress(0x05)

    def read(self):
        """Returns the readings, or None when the PZEM does not answer."""
        try:
            if self.dev.read():
                return {
                    "voltage": self.dev.getVoltage(),
                    "current": self.dev.getCurrent(),
                    "power": self.dev.getActivePower(),
                    "energy": self.dev.getActiveEnergy(),
                    "frequency": self.dev.getFrequency(),
                    "power_factor": self.dev.getPowerFactor(),
                }
        except Exception as e:
            print("PZEM error:", e)
        return None
