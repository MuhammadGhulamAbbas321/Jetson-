# Jetson Nano internet through an ESP32 (T-Call) over USB, with WiFi control from the Nano

The ESP32 joins WiFi and shares it with the Jetson over a USB serial (PPP) link.
A custom firmware lets you change the WiFi (normal or eduroam-style WPA2-Enterprise)
from the Nano, with no laptop and no reflashing.

```
 WiFi ))))  [ ESP32 T-Call ]  ==== USB cable ====  [ Jetson Nano ]
            PPP server + NAT      /dev/ttyUSB0       pppd client -> ppp0
                 ^                                          |
                 +---- control port 192.168.11.1:5000 <-----+  (espwifi.py)
```

> Status: the firmware built and flashed fine. It has **not** been tested on real hardware
> yet, so treat the Nano steps as the first test. Expected speed is under 1 Mbit/s at 921600 baud.

---

## Part 1: Windows laptop (one time)

Use the **ESP-IDF shell**, started with `eim shell`, in a **normal** PowerShell
(not "Run as administrator").

### 1.1 Install
```powershell
winget install Espressif.EIM-CLI
eim install -i v5.4.2
```
If the build later fails with `cannot execute 'cc1'`, the compiler download is incomplete
(about 151 MB instead of over 1 GB). Reinstall it with
`python $env:IDF_PATH\tools\idf_tools.py install xtensa-esp-elf` and move it into
`C:\Espressif\tools\xtensa-esp-elf`.

### 1.2 Get the example
```powershell
mkdir C:\esp -Force
cd C:\esp
git clone https://github.com/espressif/esp-protocols.git
cd C:\esp\esp-protocols\components\eppp_link\examples\slave
idf.py set-target esp32
```
Run `set-target` only once. It wipes saved settings.

### 1.3 Replace the firmware file
Copy the provided `eppp_slave.c` over `main\eppp_slave.c` (keep a backup first):
```powershell
Copy-Item main\eppp_slave.c main\eppp_slave.c.bak
Copy-Item "C:\Users\<you>\Downloads\eppp_slave.c" main\eppp_slave.c -Force
Select-String -Path main\eppp_slave.c -Pattern "cmd_setent" | Select-Object -First 1
```
The last command should print a line.

### 1.4 Settings (instead of menuconfig)
The WiFi here is only a placeholder. The Nano sets the real one later.
```powershell
Set-Content sdkconfig.defaults @('CONFIG_LWIP_IP_FORWARD=y', 'CONFIG_LWIP_IPV4_NAPT=y', 'CONFIG_LWIP_TCPIP_TASK_STACK_SIZE=4096', 'CONFIG_PARTITION_TABLE_SINGLE_APP_LARGE=y', 'CONFIG_EPPP_LINK_USES_PPP=y', 'CONFIG_EPPP_LINK_DEVICE_UART=y', 'CONFIG_EXAMPLE_UART_TX_PIN=1', 'CONFIG_EXAMPLE_UART_RX_PIN=3', 'CONFIG_EXAMPLE_UART_BAUDRATE=921600', 'CONFIG_ESP_CONSOLE_NONE=y', 'CONFIG_LOG_DEFAULT_LEVEL_NONE=y', 'CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y', 'CONFIG_ESP_WIFI_ENTERPRISE_SUPPORT=y', 'CONFIG_ESP_WIFI_SSID="temp"', 'CONFIG_ESP_WIFI_PASSWORD="12345678"')
Remove-Item sdkconfig -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
idf.py reconfigure
```
Check the result:
```powershell
Select-String -Path sdkconfig -Pattern "EPPP_LINK_USES_PPP|EXAMPLE_UART|ESP_CONSOLE_NONE|LOG_DEFAULT_LEVEL_NONE|BOOTLOADER_LOG_LEVEL_NONE|ENTERPRISE_SUPPORT"
```
You should see pins 1 and 3, baud 921600, and `NONE=y` for console and both log levels.

Why logs are off: the ESP32 prints on the same wires the PPP data uses, so any log text breaks the link.

### 1.5 Build and flash
```powershell
idf.py build
[System.IO.Ports.SerialPort]::GetPortNames()      # confirm the port, e.g. COM3
idf.py -p COM3 flash
```
If flashing hangs on "Connecting....", hold the **BOOT** button on the T-Call.
A good flash ends with `Hard resetting via RTS pin...`.

If the build fails with an `ldgen.py ... Bad file descriptor` traceback, close any
administrator PowerShell, open a normal one, delete the `build` folder and build again.

---

## Part 2: Jetson Nano

### 2.1 One-time preparation (needs other internet, e.g. Ethernet)
```bash
sudo apt update && sudo apt install -y ppp
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
```
Copy `espwifi.py` onto the Nano (USB stick or `scp`).

### 2.2 Connect and test the link
Plug the T-Call into the Nano. **Wait about a minute.** The ESP32 first tries the
placeholder WiFi, gives up after a few tries, then starts the PPP link.
```bash
ls /dev/ttyUSB*
sudo pppd /dev/ttyUSB0 921600 192.168.11.2:192.168.11.1 \
  modem local noauth nocrtscts nodetach debug
```
Success shows `local IP address 192.168.11.2` and `remote IP address 192.168.11.1`.
This does not change your default route yet, so your other internet keeps working.

In a second terminal:
```bash
ping -c 3 192.168.11.1
python3 espwifi.py status
```

### 2.3 Set the WiFi
Normal WiFi (2.4 GHz only, password 8 to 63 characters):
```bash
python3 espwifi.py scan
python3 espwifi.py set "My WiFi" "my password"
```
Eduroam-style WPA2-Enterprise (PEAP/MSCHAPv2):
```bash
python3 espwifi.py setent eduroam "yourname@youruni.edu" "your password" "anonymous@youruni.edu"
```
The last argument (outer identity) is optional. Your university's IT page gives the exact formats.

Check after about 20 seconds:
```bash
python3 espwifi.py status      # want connected=1
```

### 2.4 Use it for internet
Press Ctrl+C in the pppd terminal, then restart with routes:
```bash
sudo pppd /dev/ttyUSB0 921600 192.168.11.2:192.168.11.1 \
  modem local noauth nocrtscts nodetach debug \
  defaultroute replacedefaultroute
ping -c 3 8.8.8.8
ping -c 3 google.com
```
If only the name fails, set DNS: `echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf`.
If a manual edit does not stick, add `usepeerdns` to the pppd options.

### 2.5 Start automatically (optional)
Create `/etc/ppp/peers/esp32`:
```
/dev/ttyUSB0
921600
192.168.11.2:192.168.11.1
modem
local
noauth
nocrtscts
defaultroute
replacedefaultroute
persist
maxfail 0
holdoff 5
```
Then `sudo pon esp32` to start and `sudo poff esp32` to stop.

---

## `espwifi.py` commands

| Command | What it does |
|---|---|
| `python3 espwifi.py status` | Connection state, SSID, mode, IP |
| `python3 espwifi.py scan` | Nearby networks with signal strength |
| `python3 espwifi.py set "ssid" "password"` | Normal WiFi |
| `python3 espwifi.py setent ssid user pass [identity]` | WPA2-Enterprise |
| `python3 espwifi.py ca ca.pem` | Upload the network's server CA certificate (PEM) |
| `python3 espwifi.py clearca` | Remove the saved CA certificate |
| `python3 espwifi.py reset` | Forget everything, back to the built-in WiFi |

Limits: SSID, identity and username cannot contain `|`. Normal WiFi passwords must be
8 to 63 characters. The CA file must be PEM text under 4000 bytes.

The control port is bound to the PPP address and only accepts connections from
`192.168.11.x`, so devices on the WiFi side cannot reach it.

---

## Eduroam notes

- The ESP32 only works on **2.4 GHz**. Your laptop may show 5 GHz, but the same network
  usually has a 2.4 GHz side too.
- **Upload the CA certificate.** Without `espwifi.py ca`, the ESP32 does not verify the
  network, so a fake "eduroam" access point could capture your password. Get the RADIUS CA
  (PEM) from your university's eduroam setup page.
- Only PEAP/MSCHAPv2 is supported. If your network uses TTLS, the firmware needs a change.
- Check your university's rules on sharing a connection with another device.
- The username and password are stored in the ESP32's flash. Do not share the device
  or its firmware dump.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `/dev/ttyUSB0` missing | Use a data cable. Check `dmesg \| tail` |
| pppd `LCP: timeout` | Wait a minute after plugging in. Check the baud is 921600 on both sides |
| ESP32 resets when pppd opens the port | Wait about 3 s after plugging in, or run `stty -F /dev/ttyUSB0 -hupcl` first |
| `ppp0` is up but no internet | Run `python3 espwifi.py status`. Check `ip route` shows `ppp0` as default |
| `status` shows `connected=0` | Wrong password, or a 5 GHz-only network. Run `scan` to see what the ESP32 can hear |
| `espwifi.py` times out | The link is down. Check `ping 192.168.11.1` first |
| Wrong WiFi saved | `python3 espwifi.py reset`, then set it again |

To go back to the plain Espressif example: restore `main\eppp_slave.c.bak`, rebuild and flash.
