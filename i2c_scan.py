#!/usr/bin/env python3
"""Scan I2C buses/addresses and serial ports on a Jetson, read MLX90614 if found.

Usage:
    sudo python3 i2c_scan.py            # scan all buses (skips display bus >= 100)
    sudo python3 i2c_scan.py --bus 1    # scan only bus 1 (header pins 3 and 5)
"""
import argparse
import glob
import re
import time

try:
    from smbus2 import SMBus        # pip3 install smbus2
except ImportError:
    from smbus import SMBus         # fallback: sudo apt install python3-smbus

MLX_ADDR = 0x5A
REG_TA, REG_TOBJ1 = 0x06, 0x07
READ_COUNT = 5
READ_DELAY = 0.5


def list_i2c_buses(include_display=False):
    buses = sorted(int(re.search(r"i2c-(\d+)", p).group(1))
                   for p in glob.glob("/dev/i2c-*"))
    if not include_display:
        buses = [b for b in buses if b < 100]   # i2c-101 is the display bus
    return buses


def scan_bus(bus_num):
    """Return list of responding addresses on a bus."""
    found = []
    try:
        with SMBus(bus_num) as bus:
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)          # same probe style as i2cdetect
                    found.append(addr)
                except OSError:
                    pass
    except (PermissionError, FileNotFoundError) as e:
        print(f"  bus {bus_num}: cannot open ({e}) -> try sudo or add user to i2c group")
    return found


def read_mlx90614(bus_num, addr=MLX_ADDR):
    """Return (ambient_C, object_C)."""
    with SMBus(bus_num) as bus:
        ta = bus.read_word_data(addr, REG_TA)
        to = bus.read_word_data(addr, REG_TOBJ1)
    return ta * 0.02 - 273.15, to * 0.02 - 273.15


def list_serial_ports():
    return sorted(glob.glob("/dev/ttyTHS*") +
                  glob.glob("/dev/ttyUSB*") +
                  glob.glob("/dev/ttyACM*"))


def main():
    parser = argparse.ArgumentParser(description="I2C scan + MLX90614 reader")
    parser.add_argument("--bus", type=int, help="scan only this bus number")
    args = parser.parse_args()

    print("=== I2C buses ===")
    buses = [args.bus] if args.bus is not None else list_i2c_buses()
    if not buses:
        print("  No /dev/i2c-* devices found.")

    results = {}
    for b in buses:
        addrs = scan_bus(b)
        results[b] = addrs
        shown = ", ".join(f"0x{a:02X}" for a in addrs) or "none"
        print(f"  bus {b}: {shown}")

    print("\n=== Serial ports ===")
    ports = list_serial_ports()
    if ports:
        for p in ports:
            print("  ", p)
    else:
        print("   none found")

    print("\n=== Sensor readings ===")
    any_read = False
    for b, addrs in results.items():
        if MLX_ADDR not in addrs:
            continue
        any_read = True
        for _ in range(READ_COUNT):
            try:
                amb, obj = read_mlx90614(b)
                print(f"  bus {b} 0x{MLX_ADDR:02X}: ambient={amb:.2f} C  object={obj:.2f} C")
            except OSError as e:
                print(f"  bus {b}: read error {e}")
            time.sleep(READ_DELAY)

    if not any_read:
        print("  No MLX90614 found at 0x5A on any scanned bus.")
        print("  Check wiring/contact (SDA pin 3, SCL pin 5, GND pin 9, 3V3 pin 1).")


if __name__ == "__main__":
    main()
