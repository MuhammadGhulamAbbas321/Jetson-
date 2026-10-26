#!/usr/bin/env python3
"""Simple internet speed test for the Jetson (standard library only).

  python3 speedtest.py                 # 2 MB download, 0.5 MB upload
  python3 speedtest.py --down-mb 5     # bigger download
  python3 speedtest.py --skip-upload   # latency + download only

Over the ESP32 link expect well under 1 Mbit/s at 921600 baud, so the
defaults are small. Larger sizes just take longer (2 MB at 0.5 Mbit/s = ~32 s).
Results are rough: they include protocol overhead and the connection setup
of each request.
"""
import argparse
import socket
import subprocess
import sys
import time
import urllib.request

# The first server lets us choose the size. The fallback has a fixed size,
# so we simply stop reading after the amount we want.
DOWN_URLS = [
    "https://speed.cloudflare.com/__down?bytes={n}",
    "http://speedtest.tele2.net/10MB.zip",
]
UP_URL = "https://speed.cloudflare.com/__up"
HEADERS = {"User-Agent": "Mozilla/5.0 (speedtest.py)"}


def mbit(nbytes, seconds):
    return nbytes * 8 / seconds / 1e6 if seconds > 0 else 0.0


def show_route():
    try:
        out = subprocess.run(["ip", "route", "get", "1.1.1.1"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        print("Route to the internet:", out.splitlines()[0] if out else "unknown")
        if "ppp0" not in out:
            print("  Note: traffic is NOT going through ppp0, so this does not measure the ESP32 link.")
    except Exception:
        print("Route to the internet: could not check")


def latency(host="1.1.1.1", port=443, tries=5):
    times = []
    for _ in range(tries):
        t0 = time.time()
        try:
            with socket.create_connection((host, port), timeout=5):
                times.append((time.time() - t0) * 1000)
        except OSError:
            pass
        time.sleep(0.2)
    if not times:
        print("Latency: failed (no connection)")
        return False
    print("Latency: min %.0f ms, avg %.0f ms (%d/%d replies)" %
          (min(times), sum(times) / len(times), len(times), tries))
    return True


def download(nbytes, timeout=60):
    for template in DOWN_URLS:
        url = template.format(n=nbytes)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                t0 = time.time()
                got = 0
                while got < nbytes:
                    chunk = r.read(min(16384, nbytes - got))
                    if not chunk:
                        break
                    got += len(chunk)
                    sys.stdout.write("\rDownload: %d / %d KB" % (got // 1024, nbytes // 1024))
                    sys.stdout.flush()
                secs = time.time() - t0
            if got < nbytes // 2:
                raise OSError("server sent too little data")
            print("\rDownload: %.2f Mbit/s  (%d KB in %.1f s, from %s)" %
                  (mbit(got, secs), got // 1024, secs, url.split("/")[2]))
            return True
        except Exception as e:
            print("\rDownload from %s failed: %s" % (url.split("/")[2], e))
    return False


def upload(nbytes, timeout=60):
    data = b"0" * nbytes
    headers = dict(HEADERS)
    headers["Content-Type"] = "application/octet-stream"
    try:
        req = urllib.request.Request(UP_URL, data=data, headers=headers, method="POST")
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        secs = time.time() - t0
        print("Upload:   %.2f Mbit/s  (%d KB in %.1f s)" % (mbit(nbytes, secs), nbytes // 1024, secs))
        return True
    except Exception as e:
        print("Upload failed: %s" % e)
        return False


def main():
    ap = argparse.ArgumentParser(description="Simple internet speed test")
    ap.add_argument("--down-mb", type=float, default=2.0, help="download size in MB (default 2)")
    ap.add_argument("--up-mb", type=float, default=0.5, help="upload size in MB (default 0.5)")
    ap.add_argument("--skip-upload", action="store_true", help="skip the upload test")
    args = ap.parse_args()

    show_route()
    if not latency():
        sys.exit("No internet connection. Check 'python3 espwifi.py status' and 'ip route'.")
    download(int(args.down_mb * 1024 * 1024))
    if not args.skip_upload:
        upload(int(args.up_mb * 1024 * 1024))


if __name__ == "__main__":
    main()
