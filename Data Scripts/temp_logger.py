#!/usr/bin/env python3
"""Read a GY-906 (MLX90614) IR temperature sensor on a Jetson Nano using Linux SMBus
and save every reading to CSV.

Wiring: VCC -> Pin 1 (3.3V), GND -> Pin 6 (GND), SDA -> Pin 3, SCL -> Pin 5
Requires: sudo apt install -y python3-smbus
Check detection first:  sudo i2cdetect -y -r 1   (should show 5a)

CSV is saved to: data/<date>/temperature/temperature_<date>_<time>.csv
"""

import csv
import os
import sys
import time
from datetime import datetime

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
    # Folder: data/<date>/temperature/temperature_<date>_<time>.csv
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    folder = os.path.join("data", date_str, "temperature")
    os.makedirs(folder, exist_ok=True)
    csv_path = os.path.join(folder, f"temperature_{date_str}_{time_str}.csv")

    print("GY-906 / MLX90614 (SMBus)")
    print("=========================")
    print("Saving to:", csv_path)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "ambient_c", "object_c"])

        try:
            while True:
                try:
                    ambient = read_temperature(REG_AMBIENT)
                    object_temp = read_temperature(REG_OBJECT)
                except (OSError, ValueError) as e:
                    print(f"Sensor error: {e}")
                    print("Sensor not responding at 0x5A. Check wiring/soldering "
                          "and run: sudo i2cdetect -y -r 1")
                    time.sleep(2)
                    continue

                ts = datetime.now().isoformat(timespec="milliseconds")
                writer.writerow([ts, f"{ambient:.2f}", f"{object_temp:.2f}"])
                f.flush()  # write to disk immediately

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
