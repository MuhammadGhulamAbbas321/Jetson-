# Jetson GPS Reader (NEO-6M / ML025)

A simple Python script to read live GPS data (latitude, longitude, altitude, satellite count) from a NEO-6M GPS module connected to a Jetson Nano's UART pins.

## Hardware Wiring

| GPS Pin | Jetson Pin       |
|---------|------------------|
| VCC     | Pin 2 (5V)       |
| GND     | Pin 6 (GND)      |
| TX      | Pin 10 (RXD)     |
| RX      | Pin 8 (TXD) *(optional — only needed to send config commands)* |

Serial device used: `/dev/ttyTHS1` (Jetson's hardware UART on pins 8/10).

If that port doesn't work, check available ports:
```bash
ls /dev/tty*
```
And confirm the pins are set to UART mode:
```bash
sudo /opt/nvidia/jetson-io/jetson-io.py
```

## Requirements

- Python 3
- `pyserial`
- `pynmea2`

## Installation

Check if the libraries are already installed:
```bash
python3 -c "import serial, pynmea2; print('OK - libraries working')"
```

If that fails with a `ModuleNotFoundError`, install them:
```bash
pip3 install pyserial pynmea2 --break-system-packages
```

If pip alone doesn't work or you get permission errors, use:
```bash
sudo pip3 install pyserial pynmea2 --break-system-packages
```

## Usage

Run the script:
```bash
python3 gps.py
```

If you get a `Permission denied` error on the serial port, either run with `sudo`:
```bash
sudo python3 gps.py
```

Or (recommended, so you don't need `sudo` every time) add your user to the `dialout` group once, then log out and back in:
```bash
sudo usermod -aG dialout $USER
```

## Notes

- The GPS needs a clear view of the sky to get a satellite fix. Cold start can take 30 seconds to 2 minutes.
- The script prints "Waiting for fix..." until a valid `$GPGGA`/`$GNGGA` sentence with `gps_qual > 0` is received.
- Press `Ctrl+C` to stop the script cleanly.
