import csv
import os
from datetime import datetime

import serial
import pynmea2

PORT = "/dev/ttyTHS1"
BAUD = 9600

# Folder: data/<date>/gps/gps_<date>_<time>.csv
now = datetime.now()
date_str = now.strftime("%Y-%m-%d")
time_str = now.strftime("%H%M%S")

folder = os.path.join("data", date_str, "gps")
os.makedirs(folder, exist_ok=True)
csv_path = os.path.join(folder, f"gps_{date_str}_{time_str}.csv")

ser = serial.Serial(PORT, BAUD, timeout=1)
print("Reading GPS data... (Ctrl+C to stop)")
print("Saving to:", csv_path)

with open(csv_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "latitude", "longitude", "altitude_m", "satellites"])

    while True:
        try:
            line = ser.readline().decode("ascii", errors="replace").strip()

            if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                data = pynmea2.parse(line)

                if data.gps_qual and int(data.gps_qual) > 0:
                    ts = datetime.now().isoformat(timespec="milliseconds")
                    writer.writerow([ts, data.latitude, data.longitude,
                                     data.altitude, data.num_sats])
                    f.flush()  # write to disk immediately

                    print("Latitude:", data.latitude)
                    print("Longitude:", data.longitude)
                    print("Altitude:", data.altitude, "m")
                    print("Satellites:", data.num_sats)
                    print("-" * 30)
                else:
                    print("Waiting for fix...")

        except KeyboardInterrupt:
            print("Stopped by user")
            break
        except Exception as e:
            print("Error:", e)

ser.close()
