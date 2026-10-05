#!/usr/bin/env python3
"""Read a GY-906 (MLX90614) on a Jetson Nano using Adafruit CircuitPython (Blinka).

Wiring: VCC -> Pin 1 (3.3V), GND -> Pin 6 (GND), SDA -> Pin 3, SCL -> Pin 5
Requires: pip3 install adafruit-circuitpython-mlx90614
Check detection first:  sudo i2cdetect -y -r 1   (should show 5a)
"""

import sys
import time

import board
import busio
import adafruit_mlx90614

ADDRESS = 0x5A  # default MLX90614 address


def main():
    i2c = busio.I2C(board.SCL, board.SDA)

    try:
        mlx = adafruit_mlx90614.MLX90614(i2c, address=ADDRESS)
    except (ValueError, OSError) as e:
        print(f"Could not find the sensor at 0x{ADDRESS:02X}: {e}")
        print("Check wiring/soldering and run: sudo i2cdetect -y -r 1")
        return 1

    print("GY-906 / MLX90614 (Blinka)")
    print("==========================")

    try:
        while True:
            try:
                ambient = mlx.ambient_temperature
                object_temp = mlx.object_temperature
            except (OSError, RuntimeError) as e:
                print(f"I2C read error: {e}")
                time.sleep(2)
                continue
            print(f"Ambient Temperature : {ambient:.2f} °C")
            print(f"Object Temperature  : {object_temp:.2f} °C")
            print("-----------------------------")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        i2c.deinit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
