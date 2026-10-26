#!/usr/bin/env python3
"""Change the ESP32's WiFi from the Jetson (works over the PPP link).

  python3 espwifi.py status
  python3 espwifi.py scan
  python3 espwifi.py set "My WiFi" "my password"
  python3 espwifi.py setent eduroam "user@uni.edu" "password" ["anonymous@uni.edu"]
  python3 espwifi.py ca /path/to/ca.pem
  python3 espwifi.py clearca
  python3 espwifi.py reset

setent: the optional last argument is the outer (anonymous) identity.
        If you leave it out, the username is used.
ca:     PEM text file with your network's RADIUS server CA certificate.
        Without it the ESP32 does NOT verify the network it connects to.
"""
import socket
import sys

HOST, PORT = "192.168.11.1", 5000


def send(line, payload=b""):
    with socket.create_connection((HOST, PORT), timeout=20) as s:
        s.settimeout(20)
        s.sendall(line.encode() + b"\n" + payload)
        data = b""
        while True:
            chunk = s.recv(1024)
            if not chunk:
                break
            data += chunk
    print(data.decode(errors="replace"), end="")


def check_no_pipe(*values):
    for v in values:
        if "|" in v:
            sys.exit("This field must not contain '|': %s" % v)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0].lower()

    if cmd == "status" and len(args) == 1:
        send("STATUS")
    elif cmd == "scan" and len(args) == 1:
        send("SCAN")
    elif cmd == "reset" and len(args) == 1:
        send("RESET")
    elif cmd == "clearca" and len(args) == 1:
        send("CA|0")
    elif cmd == "set" and len(args) in (2, 3):
        ssid = args[1]
        password = args[2] if len(args) == 3 else ""
        check_no_pipe(ssid)
        send("SET|%s|%s" % (ssid, password))
    elif cmd == "setent" and len(args) in (4, 5):
        ssid, user, password = args[1], args[2], args[3]
        identity = args[4] if len(args) == 5 else ""
        check_no_pipe(ssid, user, identity)
        send("SETENT|%s|%s|%s|%s" % (ssid, identity, user, password))
    elif cmd == "ca" and len(args) == 2:
        with open(args[1], "rb") as f:
            pem = f.read().replace(b"\r\n", b"\n")
        if b"BEGIN CERTIFICATE" not in pem:
            sys.exit("That file is not a PEM certificate (no 'BEGIN CERTIFICATE').")
        if len(pem) > 4000:
            sys.exit("Certificate file is too big (max 4000 bytes). Send only the CA you need.")
        send("CA|%d" % len(pem), pem)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
