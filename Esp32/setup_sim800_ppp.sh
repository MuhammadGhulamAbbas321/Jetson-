#!/bin/bash
# Creates the PPP config files for the ESP32 T-Call (SIM800L) on the Jetson.
# Usage:  sudo bash setup_sim800_ppp.sh YOUR_APN [/dev/ttyUSB0]
# Example: sudo bash setup_sim800_ppp.sh internet

APN="${1:-}"
PORT="${2:-/dev/ttyUSB0}"

if [ -z "$APN" ]; then
  echo "Usage: sudo bash $0 YOUR_APN [serial_port]"
  exit 1
fi

if [ "$EUID" -ne 0 ]; then
  echo "Run with sudo."
  exit 1
fi

if ! command -v pppd >/dev/null 2>&1 || ! command -v chat >/dev/null 2>&1; then
  echo "pppd/chat not found. Install the ppp package first (offline: sudo dpkg -i ppp_*.deb)."
  exit 1
fi

mkdir -p /etc/ppp/peers

cat > /etc/ppp/chat-sim800 <<EOF
ABORT "NO CARRIER"
ABORT "ERROR"
ABORT "NO DIALTONE"
ABORT "BUSY"
TIMEOUT 30
"" "AT"
OK "ATE0"
OK "AT+CGDCONT=1,\"IP\",\"$APN\""
OK "ATD*99#"
CONNECT ""
EOF

cat > /etc/ppp/peers/sim800 <<EOF
$PORT
115200
noauth
local
nocrtscts
defaultroute
usepeerdns
persist
connect "/usr/sbin/chat -v -s -f /etc/ppp/chat-sim800"
EOF

echo "Done. Files created:"
echo "  /etc/ppp/chat-sim800"
echo "  /etc/ppp/peers/sim800"
echo
echo "To connect:"
echo "  sudo stty -F $PORT 115200 -hupcl"
echo "  sudo pppd call sim800 nodetach"
echo
echo "Then in another terminal:  ifconfig ppp0  and  ping -c 3 8.8.8.8"
