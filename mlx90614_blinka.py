#!/usr/bin/env python3
"""Read a GY-906 (MLX90614) on a Jetson Nano using Adafruit CircuitPython (Blinka).

Requires: pip3 install adafruit-circuitpython-mlx90614
"""

import time
import board
import busio
import adafruit_mlx90614

i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90614.MLX90614(i2c)

print("GY-906 / MLX90614 (Blinka)")
print("==========================")

try:
    while True:
        print(f"Ambient Temperature : {mlx.ambient_temperature:.2f} °C")
        print(f"Object Temperature  : {mlx.object_temperature:.2f} °C")
        print("-----------------------------")
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopped.")
