# Tenda AX300 USB Wi-Fi Adapter on Jetson Nano: Installation Guide

Adapter USB ID: `a69c:5721` (AICSemi AIC8800 family, shows up first as a fake USB "CD-ROM / mass storage" device)
Board: Jetson Nano (JetPack 4.x, Ubuntu 18.04, aarch64, kernel 4.9-tegra)
Situation: the Jetson has **no internet**, so everything is downloaded on another PC and copied over with a USB drive.

> **Honest note:** the AIC8800 driver projects are mainly tested on kernels 5.10 and newer. The Jetson Nano uses the old 4.9 kernel, so the build step may fail. Section 8 explains what to do if it does. This guide is not tested on a real Jetson Nano.

---

## 1. How the adapter works (why it needs two steps)

1. When plugged in, the adapter appears as a storage device (`a69c:5721`, "Aic MSC"). It carries a Windows driver and does **no Wi-Fi** in this state.
2. It must be "ejected" (mode-switched). It then re-appears as a Wi-Fi device (usually `a69c:8d80`, later `a69c:8d81`).
3. A kernel driver (`aic_load_fw` + `aic8800_fdrv`) and firmware files must be installed so Linux can use it.

---

## 2. Check your Jetson first

Run on the Jetson:

```bash
lsusb | grep -i a69c                 # should show a69c:5721
uname -r                             # kernel version (expect 4.9.x-tegra)
cat /etc/nv_tegra_release | head -1  # JetPack / L4T release
ls /lib/modules/$(uname -r)/build    # kernel headers must exist
gcc --version && make --version      # compiler tools must exist
```

- If `build` is missing, you need the kernel headers/sources for your L4T version (see Section 8).
- `gcc` and `make` are normally already present on JetPack.

---

## 3. Download everything on a PC with internet

On a PC (Linux, Windows with Git, or macOS):

```bash
git clone --depth 1 https://github.com/shenmintao/aic8800d80.git
# Backup option, in case the first one does not build:
git clone --depth 1 https://github.com/radxa-pkg/aic8800.git
```

Optional but helpful (usually only needed if `eject` is missing on the Jetson):
- `usb-modeswitch` and `usb-modeswitch-data` `.deb` files for **Ubuntu 18.04 (bionic) arm64**, from packages.ubuntu.com.

Copy the cloned folder(s) to a USB flash drive.

> Do not use a Wi-Fi adapter as the transfer medium. Use a normal flash drive.

---

## 4. Copy the files to the Jetson

```bash
# Insert the flash drive, then:
lsblk                                  # find the drive, e.g. /dev/sda1
sudo mount /dev/sda1 /mnt              # change sda1 to match yours
cp -r /mnt/aic8800d80 ~/
sudo umount /mnt
cd ~/aic8800d80
```

---

## 5. Switch the adapter out of storage mode

Plug in the AX300, then try the simplest method first (no extra packages):

```bash
lsblk                                  # the adapter shows up as a small disk, e.g. sdb
sudo eject /dev/sdb                    # use your disk name
sleep 3
lsusb | grep -i a69c                   # should now show a69c:8d80 (or 8d81)
```

If `eject` does not work, use usb-modeswitch (install the `.deb` files from Section 3 with `sudo dpkg -i *.deb`):

```bash
sudo usb_modeswitch -v a69c -p 5721 -KQ
```

If the ID changed from `5721` to `8d80`/`8d81`, the switch worked.

---

## 6. Build and install the driver

```bash
cd ~/aic8800d80

# Remove any old AIC firmware first (ignore errors if none exist)
sudo rm -rf /lib/firmware/aic8800*

cd drivers/aic8800
make -j4
sudo make install
```

The install step copies the kernel modules and the firmware to `/lib/firmware/`. Then load the driver:

```bash
sudo depmod -a
sudo modprobe aic_load_fw
sudo modprobe aic8800_fdrv
```

If the repository README uses different module names or steps, follow the README of the folder you cloned, since the project layout can change between versions.

---

## 7. Verify and connect

```bash
dmesg | tail -30                       # look for aic8800 messages, no errors
lsusb | grep -i a69c                   # a69c:8d81 means fully working mode
ip link                                # a new wlan0 (or wlx...) interface should appear
iw dev
```

Connect to Wi-Fi:

```bash
nmcli device wifi list
sudo nmcli device wifi connect "YourSSID" password "YourPassword"
ping -c 3 google.com
```

Make the mode switch automatic on every plug-in: the driver's `make install` normally installs udev rules for this. If it does not, repeat Section 5 after each boot.

---

## 8. Troubleshooting

| Problem | What to try |
|---|---|
| `/lib/modules/$(uname -r)/build` missing | Install the kernel headers/sources for your exact L4T release (`nvidia-l4t-kernel-headers` if available, or the L4T public kernel sources from NVIDIA downloaded on the PC). |
| `make` fails with compile errors (very likely on kernel 4.9) | Try the other repository (`radxa-pkg/aic8800`) or an older branch/tag of the driver, since older versions target older kernels. Errors about missing kernel functions mean the driver is too new for 4.9. |
| Driver loads but no `wlan0` | The adapter is probably still in storage mode: repeat Section 5. Check `lsusb` for `5721`. |
| `modprobe` says module not found | Run `sudo depmod -a`, confirm `make install` finished without errors. |
| Firmware load errors in `dmesg` | Check that `/lib/firmware/aic8800*` exists and was copied by `make install`. |
| Adapter works then stops after reboot | Load modules manually (Section 6) or add the module names to `/etc/modules-load.d/aic8800.conf`. |
| Wi-Fi works but is slow or drops | Use a USB 3.0 port and a short cable. Check `dmesg` for USB resets. |

### If the driver will not build on kernel 4.9

- **Phone USB tethering:** an Android phone with USB tethering gives the Jetson internet through its USB port, and the Jetson will see it as a network interface. This is often the easiest way to get online and install packages.
- **Ethernet:** plug the Jetson directly into a router.
- **A different adapter:** adapters with drivers that support old kernels (for example, some Realtek-based ones) are an easier fit for Jetson Nano than the AIC8800 chipset.

---

## 9. Quick reference

```bash
lsusb | grep -i a69c                    # 5721 = storage mode, 8d80/8d81 = Wi-Fi mode
sudo eject /dev/sdX                     # switch modes
sudo usb_modeswitch -v a69c -p 5721 -KQ # alternative switch
dmesg | tail -30                        # driver/firmware messages
ip link                                 # find the wlan interface
```
