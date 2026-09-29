import time
from smbus2 import SMBus

BUS = 1          # Jetson pins 3 (SDA) and 5 (SCL) = I2C bus 1
ADDR = 0x5A      # MLX90614 address
REG_AMBIENT = 0x06
REG_OBJECT = 0x07


def read_temp(bus, reg):
    raw = bus.read_word_data(ADDR, reg)
    return raw * 0.02 - 273.15   # convert to Celsius


print("Reading MLX90614... (Ctrl+C to stop)")

with SMBus(BUS) as bus:
    while True:
        try:
            ambient = read_temp(bus, REG_AMBIENT)
            obj = read_temp(bus, REG_OBJECT)
            print(f"Ambient: {ambient:.1f} C   Object: {obj:.1f} C")
        except OSError as e:
            print("Read error:", e)
        except KeyboardInterrupt:
            print("Stopped by user")
            break
        time.sleep(1)
