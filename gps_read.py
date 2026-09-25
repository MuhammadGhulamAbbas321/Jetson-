import serial

ser = serial.Serial('/dev/ttyTHS1', 9600, timeout=1)

while True:
    line = ser.readline().decode('ascii', errors='replace').strip()
    if line.startswith('$GPGGA') or line.startswith('$GPRMC'):
        print(line)
