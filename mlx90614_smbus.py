#!/usr/bin/env python3
"""Read a GY-906 (MLX90614) IR temperature sensor on a Jetson Nano using Linux SMBus.

Wiring: VCC -> Pin 1 (3.3V), GND -> Pin 6 (GND), SDA -> Pin 3, SCL -> Pin 5
Requires: sudo apt install -y python3-smbus
Check detection first:  sudo i2cdetect -y -r 1   (should show 5a)
"""

import sys
import time
import smbus

BUS = 1            # /dev/i2c-1 -> 40-pin header (pins 3 and 5)
ADDRESS = 0x5A     # default MLX90614 address
REG_AMBIENT = 0x06
REG_OBJECT = 0x07

bus = smbus.SMBus(BUS)


def read_temperature(register, retries=3):
    """Return temperature in deg C from the given RAM register."""
    last_err = None
    for _ in range(retries):
        try:
            # SMBus word reads are little-endian (low byte first), which is
            # exactly the order the MLX90614 sends, so NO byte swap is needed.
            raw = bus.read_word_data(ADDRESS, register)
        except OSError as e:
            last_err = e
            time.sleep(0.1)
            continue
        if raw & 0x8000:          # MSB set = error flag from the sensor
            last_err = ValueError("sensor reported an error flag")
            time.sleep(0.1)
            continue
        return raw * 0.02 - 273.15
    raise last_err


def main():
    print("GY-906 / MLX90614 (SMBus)")
    print("=========================")
    try:
        while True:
            try:
                ambient = read_temperature(REG_AMBIENT)
                object_temp = read_temperature(REG_OBJECT)
            except OSError as e:
                print(f"I2C error: {e}")
                print("Sensor not responding at 0x5A. Check wiring/soldering "
                      "and run: sudo i2cdetect -y -r 1")
                time.sleep(2)
                continue
            print(f"Ambient Temperature : {ambient:.2f} °C")
            print(f"Object Temperature  : {object_temp:.2f} °C")
            print("-----------------------------")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        bus.close()


if __name__ == "__main__":
    sys.exit(main())
