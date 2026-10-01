# Jetson Nano + GY-906 (MLX90614) IR Temperature Sensor

The GY-906 communicates over **I²C**. On the Jetson Nano, the 40-pin header exposes I²C bus 1 (`/dev/i2c-1`).

## Wiring

| GY-906 | Jetson Nano     |
| ------ | --------------- |
| VCC    | 3.3V — Pin 1    |
| GND    | GND — Pin 6 (Pin 9 also works) |
| SDA    | Pin 3 — I²C SDA |
| SCL    | Pin 5 — I²C SCL |

> Use **3.3V**, not 5V. Make sure header pins are soldered or firmly seated.

## 1. Check the sensor

```bash
sudo apt update
sudo apt install -y i2c-tools
ls /dev/i2c*
sudo i2cdetect -y -r 1
```

Expected: address `5a` appears in the grid.

```text
     0 1 2 3 4 5 6 7 8 9 a b c d e f
50: -- -- -- -- -- -- -- -- -- -- 5a -- -- -- -- --
```

## 2. Option A: SMBus (recommended on Jetson Nano)

Talks directly to the Linux I²C device and avoids Blinka configuration issues.

```bash
sudo apt install -y python3-smbus
python3 mlx90614_smbus.py
```

Script: [`mlx90614_smbus.py`](mlx90614_smbus.py)

## 3. Option B: Adafruit Blinka library

```bash
sudo apt install -y python3-pip
pip3 install adafruit-circuitpython-mlx90614
# if you get a permissions error:
pip3 install --user adafruit-circuitpython-mlx90614

python3 mlx90614_blinka.py
```

Script: [`mlx90614_blinka.py`](mlx90614_blinka.py)

## Sample output

```text
Ambient Temperature : 27.52 °C
Object Temperature  : 36.43 °C
-----------------------------
```

## How the SMBus conversion works

- Ambient temperature register: `0x06`, object temperature register: `0x07`
- Raw value is in units of 0.02 K, so `°C = raw * 0.02 - 273.15`
- SMBus returns the two bytes swapped, so they are swapped back before converting

## Troubleshooting

- **Empty `i2cdetect` grid / `Errno 121 Remote I/O error`**: no device is answering. Re-check SDA/SCL are not swapped, VCC is on Pin 1 (3.3V), GND is connected, and the solder joints/jumper connections are solid.
- **Permission denied on `/dev/i2c-1`**: run with `sudo`, or add your user to the `i2c` group (`sudo usermod -aG i2c $USER`, then log out and in).
- **Different bus number**: check `ls /dev/i2c*` and change `BUS` in the script.
