import serial
import pynmea2

PORT = "/dev/ttyTHS1"
BAUD = 9600

ser = serial.Serial(PORT, BAUD, timeout=1)
print("Reading GPS data... (Ctrl+C to stop)")

while True:
    try:
        line = ser.readline().decode("ascii", errors="replace").strip()

        if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
            data = pynmea2.parse(line)

            if data.gps_qual and int(data.gps_qual) > 0:
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
