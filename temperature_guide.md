# MLX90614 Temperature Sensor on Jetson Nano

## 1. Wiring (F-F jumpers, direct to Jetson)

| MLX90614 | Jetson pin |
|---|---|
| VIN | Pin 1 (3.3V) |
| GND | Pin 9 (GND) |
| SDA | Pin 3 (SDA) |
| SCL | Pin 5 (SCL) |

Use 3.3V (pin 1), not 5V.

## 2. Commands that need `sudo`

| Command | What it does |
|---|---|
| `sudo apt install -y i2c-tools` | Installs `i2cdetect` |
| `sudo usermod -a -G i2c $USER` | Lets you use the I2C bus |
| `sudo reboot` | Applies the group change |

## 3. Commands that do NOT need `sudo`

| Command | What it does |
|---|---|
| `pip3 install smbus2` | Installs the Python library |
| `i2cdetect -y -r 1` | Checks the sensor is connected |
| `nano temp.py` | Creates the script |
| `python3 temp.py` | Runs the script |

## 4. Setup (copy and paste)

```bash
sudo apt install -y i2c-tools
pip3 install smbus2
sudo usermod -a -G i2c $USER
sudo reboot
```

## 5. Check the sensor

```bash
i2cdetect -y -r 1
```

You should see `5a` in the table. If the table is empty, recheck the four wires.

## 6. Script: `nano temp.py`

Paste this, then save with **Ctrl+O**, **Enter**, **Ctrl+X**.

```python
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
```

## 7. Run

```bash
python3 temp.py
```

## 8. Reading the output

- **Ambient** is the room temperature.
- **Object** is the temperature of whatever the sensor points at, such as a forehead or hand.
- Hold the sensor 1 to 3 cm from the skin. Farther away, it averages in the background.
- Skin readings are usually a bit lower than core body temperature.

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `i2cdetect` shows an empty table | Recheck VIN, GND, SDA, SCL on pins 1, 9, 3, 5 |
| `Permission denied` | Run the `usermod` command, then `sudo reboot` |
| `ModuleNotFoundError: smbus2` | Run `pip3 install smbus2` |
| `Read error` printed repeatedly | Loose wire; reseat the jumpers |
