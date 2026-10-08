# Jetson Nano Internet via ESP32 T-Call (SIM800L, Jazz)

The T-Call runs `bridge.cpp` (a USB-to-modem pass-through). The Nano runs PPP over `/dev/ttyUSB0` and gets a `ppp0` internet interface.

> **Speed:** SIM800L is 2G only (about 20-40 kbps). Fine for SSH, small `pip` packages and small `.deb` files. Not for large downloads.

## 1. Prepare the T-Call (laptop)

1. Upload `bridge.cpp` to the T-Call with the Arduino IDE.
2. Unplug it from the laptop and plug it into a Nano USB port.
3. Wait about 10 seconds.

## 2. Check the Nano sees it

```bash
ls /dev/ttyUSB*
which pppd
```

Expected: `/dev/ttyUSB0` and `/usr/sbin/pppd`.

## 3. Create the PPP config (once)

APN for Jazz prepaid: `jazzconnect.mobilinkworld.com` (postpaid: `connect.mobilinkworld.com`).

```bash
sudo mkdir -p /etc/ppp/peers

sudo tee /etc/ppp/chat-sim800 > /dev/null <<'EOF'
ABORT "NO CARRIER"
ABORT "ERROR"
ABORT "NO DIALTONE"
ABORT "BUSY"
TIMEOUT 30
"" "AT"
OK "ATE0"
OK "AT+CGDCONT=1,\"IP\",\"jazzconnect.mobilinkworld.com\""
OK "ATD*99#"
CONNECT ""
EOF

sudo tee /etc/ppp/peers/sim800 > /dev/null <<'EOF'
/dev/ttyUSB0
115200
noauth
local
nocrtscts
noipdefault
defaultroute
usepeerdns
persist
debug
connect "/usr/sbin/chat -v -s -f /etc/ppp/chat-sim800"
EOF
```

## 4. Connect

```bash
sudo stty -F /dev/ttyUSB0 115200 -hupcl
sleep 10
sudo pppd call sim800 nodetach
```

Wait about 20 seconds. Success shows `local IP address` and `remote IP address`.

Keep this terminal open. Closing it or pressing Ctrl+C stops the internet.

## 5. Test (second terminal)

```bash
ifconfig ppp0
ping -c 3 8.8.8.8
```

If the ping works but names do not resolve:

```bash
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
ping -c 3 google.com
```

## Stop

```bash
sudo killall pppd
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `/dev/ttyUSB0` missing | Try another cable or USB port, check `dmesg \| tail` |
| `NO CARRIER` or `ERROR` | Wrong APN, no data bundle, or weak signal. Test with AT commands (`AT+CSQ`, `AT+CREG?`) |
| First attempt fails, second works | The ESP32 resets when the port opens. Wait 10 s after plugging in, then retry |
| Modem reboots while dialing | Weak USB power. Power the Nano from its barrel jack, or use a powered hub |
| Ping works, names do not | Set `nameserver 8.8.8.8` in `/etc/resolv.conf` |
| Traffic goes via another interface | Check `ip route`. The default route should point to `ppp0` |
| Port busy | Close `screen` or the Arduino Serial Monitor first |
