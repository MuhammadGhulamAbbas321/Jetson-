#!/usr/bin/env python3
"""Read a GY-906 (MLX90614) IR temperature sensor on a Jetson Nano using Linux SMBus.

Wiring: VCC -> Pin 1 (3.3V), GND -> Pin 6 (GND), SDA -> Pin 3, SCL -> Pin 5
Requires: sudo apt install -y python3-smbus
"""

import time
import smbus

BUS = 1            # /dev/i2c-1 -> 40-pin header
ADDRESS = 0x5A     # default MLX90614 address
REG_AMBIENT = 0x06
REG_OBJECT = 0x07

bus = smbus.SMBus(BUS)


def read_temperature(register):
    """Return temperature in deg C from the given RAM register."""
    data = bus.read_word_data(ADDRESS, register)
    # SMBus returns the bytes swapped relative to the MLX90614 LSB/MSB order
    data = ((data & 0xFF) << 8) | ((data >> 8) & 0xFF)
    return data * 0.02 - 273.15


def main():
    print("GY-906 / MLX90614 (SMBus)")
    print("=========================")
    try:
        while True:
            ambient = read_temperature(REG_AMBIENT)
            object_temp = read_temperature(REG_OBJECT)
            print(f"Ambient Temperature : {ambient:.2f} °C")
            print(f"Object Temperature  : {object_temp:.2f} °C")
            print("-----------------------------")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        bus.close()


if __name__ == "__main__":
    main()
