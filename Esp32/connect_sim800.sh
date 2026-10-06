#!/bin/bash
# Starts PPP internet through the ESP32 T-Call (SIM800L) bridge.
# Usage: sudo bash connect_sim800.sh [/dev/ttyUSB0]
PORT="${1:-/dev/ttyUSB0}"

if [ "$EUID" -ne 0 ]; then echo "Run with sudo."; exit 1; fi
if [ ! -e "$PORT" ]; then echo "$PORT not found. Is the ESP32 plugged in? (ls /dev/ttyUSB*)"; exit 1; fi

echo "Waiting 10 s for the ESP32 and modem to boot..."
sleep 10
stty -F "$PORT" 115200 -hupcl
echo "Starting pppd (Ctrl+C to stop)..."
pppd call sim800 nodetach
