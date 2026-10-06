# ESP32 T-Call (SIM800L) → Jetson Nano Internet

Gives a Jetson Nano internet through a **LilyGO TTGO T-Call V1.3** (ESP32-WROVER-B with onboard SIM800L).

The ESP32 acts as a **USB-to-modem bridge**. The Jetson runs PPP through it and gets a `ppp0` interface.

> **Speed warning:** SIM800L is 2G only (about 20–40 kbps). Fine for small `.deb` files, small `pip` packages and sensor data. Not suitable for PyTorch, JetPack updates or large models.

## Files

```
esp32-jetson-internet/
├── README.md
├── esp32/
│   ├── at_test.cpp          # Step 1: manual AT commands from the Serial Monitor
│   ├── internet_test.cpp    # Step 2: ESP32 itself gets internet (TinyGSM)
│   └── bridge.cpp           # Step 3: transparent bridge for the Jetson (use this one)
└── jetson/
    ├── setup_sim800_ppp.sh  # creates the PPP config files
    └── connect_sim800.sh    # starts the connection
```

## Hardware checklist

- T-Call V1.3 with a **Nano SIM** (PIN lock off, mobile data active)
- GSM antenna attached to the u.FL socket next to the SIM800L
- USB **data** cable
- Modem pins are fixed on the board: TX 27, RX 26, PWKEY 4, RST 5, POWER_ON 23

## Step 1: Test the modem (laptop, VS Code + PlatformIO)

1. Copy `esp32/at_test.cpp` to `src/main.cpp` in the PlatformIO project (only one `.cpp` with `setup()`/`loop()` in `src`).
2. `platformio.ini`:

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
    vshymanskyy/TinyGSM
    arduino-libraries/ArduinoHttpClient
```

3. Build (✓), upload (→; hold **BOOT** if it shows `Connecting......`), open the Serial Monitor (plug icon).
4. Type these, one at a time:

| Command | Good reply |
|---|---|
| `AT` | `OK` |
| `AT+CPIN?` | `+CPIN: READY` |
| `AT+CSQ` | first number above 10 |
| `AT+CREG?` | `,1` or `,5` |

If `AT` gets no reply or garbage, change `115200` to `9600` in `Serial1.begin(...)` and upload again.

## Step 2 (optional): ESP32 internet on its own

Copy `esp32/internet_test.cpp` to `src/main.cpp`, set your APN, upload. The Serial Monitor should show the operator, a local IP and `HTTP status: 200`.

Common APNs in Pakistan (verify with your carrier):

| Carrier | APN |
|---|---|
| Jazz | `jazzconnect.mobilinkworld.com` |
| Telenor | `internet` |
| Zong | `zonginternet` |
| Ufone | `ufone.internet` |

## Step 3: Bridge for the Jetson

1. Copy `esp32/bridge.cpp` to `src/main.cpp`, build and upload from the laptop.
2. Unplug the ESP32 from the laptop and plug it into a **Jetson USB port**.
3. On the Jetson, check it appears:

```bash
ls /dev/ttyUSB*
dmesg | tail
```

## Step 4: Jetson setup

### 4.1 Install ppp (offline)

The Jetson has no internet yet, so download the `ppp` package for **Ubuntu 18.04 arm64 (bionic)** on your laptop (packages.ubuntu.com), copy it over with a USB stick, then:

```bash
sudo dpkg -i ppp_*.deb
which pppd chat
```

### 4.2 Copy the scripts to the Jetson

Put the `jetson/` folder on a USB stick, or use `scp` if the Jetson is reachable on a network:

```bash
scp -r jetson/ <user>@<jetson-ip>:~/sim800/
```

### 4.3 Create the PPP config (once)

```bash
cd ~/sim800
sudo bash setup_sim800_ppp.sh YOUR_APN
```

This writes `/etc/ppp/chat-sim800` and `/etc/ppp/peers/sim800`.

### 4.4 Connect

```bash
sudo bash connect_sim800.sh
```

It waits 10 seconds for the ESP32 and modem to boot, then runs `pppd`. When it works you will see `local IP address` and `remote IP address`.

In a second terminal:

```bash
ifconfig ppp0
ping -c 3 8.8.8.8
```

Stop with **Ctrl+C**, or `sudo killall pppd`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `/dev/ttyUSB0` missing | Try another cable or port. Check `dmesg`. |
| `NO CARRIER` / `ERROR` in chat output | Wrong APN, no data plan, or no signal. Re-test with AT commands (`AT+CSQ`, `AT+CREG?`). |
| First attempt fails, second works | The ESP32 resets when the serial port opens. Wait 10 s after plugging in and retry. |
| Modem reboots during connect | Weak USB power. Use a powered hub, or add a LiPo battery to the board's battery connector. |
| `ping 8.8.8.8` works, names do not | Add `nameserver 8.8.8.8` to `/etc/resolv.conf`. |
| Traffic still goes via another interface | Check `ip route`; `defaultroute` should point at `ppp0`. |
| Upload fails (laptop) | Hold **BOOT** during `Connecting......`. Install the CP210x or CH340 driver. |
