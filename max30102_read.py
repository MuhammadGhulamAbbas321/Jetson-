#!/usr/bin/env python3
"""MAX30102 pulse / SpO2 reader for Jetson Nano (I2C bus 1, address 0x57).

Wiring (F-F jumpers): VIN -> pin 1 (3.3V), GND -> pin 9, SDA -> pin 3, SCL -> pin 5.
This board's pin order is VIN, SCL, SDA, INT, IRD, RD, GND. Leave INT/IRD/RD unconnected.

Usage:
    sudo python3 max30102_read.py --check                 # detect chip, print IDs
    sudo python3 max30102_read.py                         # full readout
    sudo python3 max30102_read.py --simple                # only BPM and SpO2
    sudo python3 max30102_read.py --log --est-log         # save raw + estimates to CSV
    sudo python3 max30102_read.py --seconds 60            # stop after 60 s

Processing overview
    * 100 Hz sampling, 18-bit ADC, red + IR LEDs.
    * Zero-phase band-pass filter (0.5-4 Hz) on each channel.
    * Heart rate: peak detection with an adaptive threshold, refractory period and
      sub-sample peak position; HR = 60*FS / median(beat intervals). It is cross-checked
      against an autocorrelation estimate and shown only when both methods agree.
    * SpO2: R = (AC_red/DC_red) / (AC_ir/DC_ir), where the red/IR AC ratio is the
      least-squares slope of the band-passed red signal on the band-passed IR signal.
      Noise that is not correlated with the pulse (electrical noise, most motion) does
      not inflate AC_red the way an RMS would, and a red/IR correlation gate rejects
      windows that are mostly noise. R is mapped with a quadratic whose default
      coefficients come from a widely used reference design. They are NOT calibrated
      for your module and this program is NOT a validated SpO2 measurement.
    * Finger detection: threshold learned from a no-finger baseline at start-up (or set
      with --finger-min), with hysteresis. Use --finger-test to check it on your hardware.
    * LED current is lowered automatically if the ADC saturates or raised if the signal
      is weak; the change is marked in the raw log.
    * FIFO overflow is detected via OVF_COUNTER (which saturates at 15, so it is only a
      lower bound). The number of dropped samples is also estimated from the host clock.

Raw CSV columns (--log)
    seq             sequential number of received samples (starts at 1)
    t_sensor_s      sample time on the sensor's 100 Hz timeline = sensor_index / FS. Regular
                    and jitter-free; advanced by the estimated dropped samples after a gap.
    t_mono_read_s   host monotonic clock (s since start) when the burst containing this
                    sample was read. All samples of one burst share this value.
    t_wall_read_s   host wall clock (epoch s) at the same moment, for aligning other logs.
    red, ir         raw 18-bit ADC counts
    finger          1 if the finger detector says present
    led             LED current register value in effect for this sample (0.2 mA per step)
    gap_est         estimated samples dropped immediately BEFORE this one (0 = none)
    gap_hw_min      hardware overflow counter for the same gap (lower bound, max 15)
    event           overflow | finger_on | finger_off | led_change (first sample after it)
Timestamps come from the host and the sensor's own clock, not from a hardware timestamp
unit. The MAX30102 has none, so precise research timing needs external synchronisation.

Estimates are for data acquisition / learning. They are NOT for medical decisions.
"""
import argparse
import csv
import math
import sys
import time
from collections import deque
from datetime import datetime

try:
    from smbus2 import SMBus        # pip3 install smbus2
except ImportError:
    from smbus import SMBus         # fallback: python3-smbus

DEFAULT_ADDR = 0x57
PART_ID_EXPECTED = 0x15

REG_FIFO_WR = 0x04       # FIFO write pointer
REG_FIFO_OVF = 0x05      # FIFO overflow counter (saturates at 15)
REG_FIFO_RD = 0x06       # FIFO read pointer
REG_FIFO_DATA = 0x07     # FIFO data port (does not auto-increment during burst reads)
REG_FIFO_CFG = 0x08
REG_MODE = 0x09
REG_SPO2 = 0x0A
REG_LED_RED = 0x0C
REG_LED_IR = 0x0D
REG_REV_ID = 0xFE
REG_PART_ID = 0xFF

FS = 100                       # sample rate in Hz (must match SPO2_CONFIG below)
WINDOW_MIN = 4 * FS            # samples needed before the first estimate
WINDOW_MAX = 6 * FS            # analysis window length
FIFO_DEPTH = 32                # MAX30102 FIFO holds 32 samples
BURST_SAMPLES = 5              # one SMBus block read is max 32 bytes = 5 samples x 6 bytes
SATURATION = 260000            # 18-bit full scale is 262143
DEFAULT_FINGER_MIN = 20000     # used only if baseline calibration is skipped/invalid
DEFAULT_SPO2_COEFFS = (-45.060, 30.354, 94.845)
LED_MIN, LED_MAX_AUTO = 0x08, 0x7F   # ~1.6 mA .. ~25 mA (0.2 mA per LSB)


# --------------------------------------------------------------------------- driver
class MAX30102:
    def __init__(self, bus_num, addr):
        self.bus = SMBus(bus_num)
        self.addr = addr

    def write(self, reg, val):
        self.bus.write_byte_data(self.addr, reg, val)

    def read(self, reg):
        return self.bus.read_byte_data(self.addr, reg)

    def part_id(self):
        return self.read(REG_PART_ID)

    def rev_id(self):
        return self.read(REG_REV_ID)

    def set_led(self, amp):
        self.write(REG_LED_RED, amp)
        self.write(REG_LED_IR, amp)

    def setup(self, led):
        self.write(REG_MODE, 0x40)                       # soft reset
        for _ in range(20):                              # reset bit self-clears
            time.sleep(0.01)
            if not self.read(REG_MODE) & 0x40:
                break
        # FIFO_CONFIG = SMP_AVE 000 (no averaging) | FIFO_ROLLOVER_EN 0 | FIFO_A_FULL 0xF.
        # Rollover is OFF: when all 32 slots are full, NEW samples are dropped and
        # OVF_COUNTER counts them. FIFO_A_FULL only drives the INT pin, which is unused.
        self.write(REG_FIFO_CFG, (0 << 5) | (0 << 4) | 0x0F)
        # SPO2_CONFIG = ADC range 4096 nA | 100 Hz sample rate | 411 us pulse (18-bit)
        self.write(REG_SPO2, (1 << 5) | (1 << 2) | 0x03)
        self.set_led(led)
        self.write(REG_FIFO_WR, 0)
        self.write(REG_FIFO_OVF, 0)
        self.write(REG_FIFO_RD, 0)
        self.write(REG_MODE, 0x03)                       # SpO2 mode: red + IR

    def read_samples(self):
        """Return (samples, lost).

        samples: list of (red, ir) currently in the FIFO.
        lost:    number of samples dropped because the FIFO was full (lower bound, the
                 hardware counter stops at 15). 0 means no loss.

        When the FIFO is completely full the write and read pointers are equal, which
        looks exactly like "empty", so OVF_COUNTER is used to tell the two apart.
        """
        wr = self.read(REG_FIFO_WR)
        rd = self.read(REG_FIFO_RD)
        ovf = self.read(REG_FIFO_OVF)
        count = (wr - rd) & (FIFO_DEPTH - 1)
        lost = 0
        if ovf:
            count = FIFO_DEPTH
            lost = ovf
        out = []
        while count > 0:
            n = min(count, BURST_SAMPLES)
            d = self.bus.read_i2c_block_data(self.addr, REG_FIFO_DATA, 6 * n)
            for k in range(n):
                o = 6 * k
                red = ((d[o] << 16) | (d[o + 1] << 8) | d[o + 2]) & 0x3FFFF
                ir = ((d[o + 3] << 16) | (d[o + 4] << 8) | d[o + 5]) & 0x3FFFF
                out.append((red, ir))
            count -= n
        return out, lost

    def close(self):
        self.bus.close()


# ----------------------------------------------------------------- signal processing
def _biquad_coeffs(kind, f, fs, q=0.7071067811865476):
    w0 = 2 * math.pi * f / fs
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * q)
    if kind == "lp":
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
    else:  # "hp"
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
    a0 = 1 + alpha
    return (b0 / a0, b1 / a0, b2 / a0, (-2 * cw) / a0, (1 - alpha) / a0)


_BANDPASS = [_biquad_coeffs("hp", 0.5, FS), _biquad_coeffs("lp", 4.0, FS)]


def _apply_biquad(x, c):
    b0, b1, b2, a1, a2 = c
    x0 = x[0]
    y_ss = x0 * (b0 + b1 + b2) / (1 + a1 + a2)     # steady-state start avoids a transient
    x1 = x2 = x0
    y1 = y2 = y_ss
    out = []
    for v in x:
        y = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out.append(y)
        x2, x1 = x1, v
        y2, y1 = y1, y
    return out


def bandpass(x):
    """Zero-phase 0.5-4 Hz band-pass (forward-backward), with odd-symmetric edge padding."""
    pad = min(150, len(x) - 1)
    left = [2 * x[0] - x[i] for i in range(pad, 0, -1)]
    right = [2 * x[-1] - x[-1 - i] for i in range(1, pad + 1)]
    y = left + list(x) + right
    for c in _BANDPASS:
        y = _apply_biquad(y, c)
    y.reverse()
    for c in _BANDPASS:
        y = _apply_biquad(y, c)
    y.reverse()
    return y[pad:pad + len(x)]


def find_peaks(sig, min_gap, thr):
    cand = [i for i in range(1, len(sig) - 1)
            if sig[i] > thr and sig[i] >= sig[i - 1] and sig[i] > sig[i + 1]]
    peaks = []
    for i in cand:
        if peaks and i - peaks[-1] < min_gap:        # refractory period: keep the taller
            if sig[i] > sig[peaks[-1]]:
                peaks[-1] = i
        else:
            peaks.append(i)
    return peaks


def _refine(sig, i):
    a, b, c = sig[i - 1], sig[i], sig[i + 1]
    d = a - 2 * b + c
    return i if d == 0 else i + 0.5 * (a - c) / d    # parabolic (sub-sample) peak position


def hr_from_peaks(sig):
    """Return (bpm or None, peak indices). HR = 60*FS / median(retained beat intervals)."""
    s_ = sorted(sig)
    p95 = s_[int(0.95 * (len(s_) - 1))]
    if p95 <= 0:
        return None, []
    peaks = find_peaks(sig, int(0.3 * FS), 0.35 * p95)   # adaptive threshold, <= ~200 bpm
    if len(peaks) < 3:
        return None, peaks
    pos = [_refine(sig, i) for i in peaks]
    iv = [b - a for a, b in zip(pos, pos[1:])]
    med = median(iv)
    good = [v for v in iv if abs(v - med) <= 0.3 * med]  # drop missed/extra beats
    if len(good) < 2:
        return None, peaks
    return 60.0 * FS / median(good), peaks


def beat_pp(sig, peaks):
    """Median peak-to-peak beat amplitude (robust against noise spikes), or None."""
    pps = []
    for a, b in zip(peaks, peaks[1:]):
        trough = min(sig[a:b + 1])
        pps.append(0.5 * ((sig[a] - trough) + (sig[b] - trough)))
    return median(pps) if pps else None


def hr_from_autocorr(sig):
    """Return (bpm, correlation strength) from the autocorrelation of the signal."""
    n = len(sig)
    mean = sum(sig) / n
    x = [v - mean for v in sig]
    e0 = sum(v * v for v in x) / n
    if e0 <= 0:
        return None, 0.0
    lo, hi = int(FS * 60 / 180), min(int(FS * 60 / 40), n // 2)
    r = {}
    for lag in range(lo - 1, hi + 2):
        r[lag] = (sum(x[i] * x[i + lag] for i in range(n - lag)) / (n - lag)) / e0
    maxima = [l for l in range(lo, hi + 1) if r[l] >= r[l - 1] and r[l] > r[l + 1]]
    if not maxima:
        return None, 0.0
    best = max(r[l] for l in maxima)
    lag = min(l for l in maxima if r[l] >= 0.85 * best)   # prefer fundamental over harmonics
    a, b, c = r[lag - 1], r[lag], r[lag + 1]
    d = a - 2 * b + c
    lag_f = lag if d == 0 else lag + 0.5 * (a - c) / d
    return 60.0 * FS / lag_f, r[lag]


def analyze(red, ir, coeffs):
    """Return dict with hr, spo2, r, corr, pi, quality for one window of raw samples."""
    fi = bandpass(ir)
    fr = bandpass(red)
    res = {"hr": None, "spo2": None, "r": None, "corr": None, "pi": None, "quality": "unclear"}

    sig = [-v for v in fi]                            # light drops during a beat
    hp, peaks = hr_from_peaks(sig)
    ha, ac_corr = hr_from_autocorr(sig)
    if hp and ha and ac_corr >= 0.3 and abs(hp - ha) <= 8:
        res["hr"] = hp
        res["quality"] = "good"

    dc_r, dc_i = sum(red) / len(red), sum(ir) / len(ir)
    sii = sum(v * v for v in fi)
    srr = sum(v * v for v in fr)
    sri = sum(a * b for a, b in zip(fr, fi))
    pp = beat_pp(sig, peaks) if peaks else None
    if pp is not None and dc_i > 0:
        res["pi"] = 100.0 * pp / dc_i                  # perfusion index, % (median beat p-p)
    if min(dc_r, dc_i, sii, srr) > 0:
        corr = sri / math.sqrt(sii * srr)              # red/IR agreement, -1..1
        beta = sri / sii                               # LS slope of red AC on IR AC
        r = beta * dc_i / dc_r                         # = (AC_red/DC_red) / (AC_ir/DC_ir)
        res["corr"], res["r"] = corr, r
        if (res["pi"] or 0) >= 0.1 and corr >= 0.9 and 0.3 <= r <= 3.0:
            a, b, c = coeffs
            res["spo2"] = max(0.0, min(100.0, a * r * r + b * r + c))
    return res


def median(values):
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


# ------------------------------------------------------------------ finger + logging
class FingerDetector:
    """Threshold with hysteresis on the mean IR level."""

    def __init__(self, thr):
        self.thr = thr
        self.present = False

    def update(self, mean_ir):
        if self.present:
            if mean_ir < 0.8 * self.thr:
                self.present = False
        elif mean_ir > self.thr:
            self.present = True
        return self.present


class Logger:
    def __init__(self, raw_path, est_path):
        self.files = []
        self.raw = self.est = None
        if raw_path:
            f = open(raw_path, "w", newline="")
            self.files.append(f)
            self.raw = csv.writer(f, lineterminator="\n")
            self.raw.writerow(["seq", "t_sensor_s", "t_mono_read_s", "t_wall_read_s", "red", "ir",
                               "finger", "led", "gap_est", "gap_hw_min", "event"])
        if est_path:
            f = open(est_path, "w", newline="")
            self.files.append(f)
            self.est = csv.writer(f, lineterminator="\n")
            self.est.writerow(["seq", "t_sensor_s", "hr_bpm", "spo2_pct", "hr_shown", "spo2_shown",
                               "R", "red_ir_corr", "PI_pct", "quality", "finger", "led"])

    def flush(self):
        for f in self.files:
            f.flush()

    def close(self):
        for f in self.files:
            f.close()


def auto_name(kind):
    return f"max30102_{datetime.now():%Y%m%d_%H%M%S}_{kind}.csv"


# ------------------------------------------------------------------------- program
def check_only(sensor, args):
    try:
        pid = sensor.part_id()
        rev = sensor.rev_id()
    except OSError as e:
        print(f"No answer at 0x{args.addr:02X} on bus {args.bus}: {e}")
        print("Check: header pins soldered, VIN on pin 1 (3.3V), GND on pin 9,")
        print("SDA on pin 3, SCL on pin 5 (this board's pin order is VIN, SCL, SDA).")
        return 1
    print(f"Found device at 0x{args.addr:02X} on bus {args.bus}")
    ok = pid == PART_ID_EXPECTED
    print(f"  Part ID: 0x{pid:02X}  ({'MAX30102 OK' if ok else 'unexpected, expected 0x15'})")
    print(f"  Rev ID : 0x{rev:02X}")
    return 0 if ok else 2


def collect_ir(sensor, seconds, discard=0.3):
    """Read for `seconds`, return IR samples after the first `discard` seconds."""
    vals = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        samples, _ = sensor.read_samples()
        if time.monotonic() - t0 > discard:
            vals.extend(ir for _, ir in samples)
        time.sleep(0.03)
    return vals


def measure_baseline(sensor, seconds=2.0):
    """Mean IR level with NO finger on the sensor."""
    vals = collect_ir(sensor, seconds)
    return sum(vals) / len(vals) if len(vals) >= 50 else None


def auto_finger_threshold(base):
    return max(base * 3.0, base + 10000, 8000)


def _stats(v):
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / len(v))
    return m, sd, min(v), max(v)


def finger_test(sensor, args):
    """Measure real no-finger and finger IR levels and check the automatic threshold."""
    if check_only(sensor, args) != 0:
        return 1
    sensor.setup(args.led)
    print("\nStep 1/2: keep your finger OFF the sensor. Measuring for 3 s...")
    off = collect_ir(sensor, 3.0)
    print("Step 2/2: place your fingertip on the sensor now (you have 3 s), then hold still...")
    collect_ir(sensor, 3.0, discard=99)            # keeps draining the FIFO while you move
    print("  measuring for 3 s...")
    on = collect_ir(sensor, 3.0)
    if len(off) < 50 or len(on) < 50:
        print("Not enough samples were read.")
        return 1
    om, osd, omin, omax = _stats(off)
    fm, fsd, fmin, fmax = _stats(on)
    thr = auto_finger_threshold(om)
    print(f"\n  no finger: mean {om:8.0f}  std {osd:6.0f}  min {omin:7d}  max {omax:7d}")
    print(f"  finger   : mean {fm:8.0f}  std {fsd:6.0f}  min {fmin:7d}  max {fmax:7d}")
    print(f"  automatic threshold (max(3*base, base+10000, 8000)) = {thr:.0f}")
    if fm < 2 * om:
        print("  Finger level is not clearly above no-finger level: press a little firmer,")
        print("  check the sensor faces the fingertip, and check LED current (--led).")
        return 1
    if omax < thr < fmin:
        print("  OK: the threshold sits between every no-finger and every finger sample.")
    else:
        mid = math.sqrt(max(om, 1) * fm)
        print("  The automatic threshold is NOT cleanly between the two ranges on your setup.")
        print(f"  Use:  --finger-min {mid:.0f}")
    return 0


def run(sensor, args):
    if check_only(sensor, args) != 0:
        return 1
    led = args.led
    sensor.setup(led)

    finger_thr = args.finger_min
    if finger_thr is None:
        if args.no_calibrate:
            finger_thr = DEFAULT_FINGER_MIN
        else:
            print("\nCalibrating: keep your finger OFF the sensor for 2 seconds...")
            base = measure_baseline(sensor)
            if base is None or base > 100000:
                finger_thr = DEFAULT_FINGER_MIN
                print(f"  Baseline unusable ({'none' if base is None else int(base)}), "
                      f"using default finger threshold {finger_thr}.")
            else:
                finger_thr = auto_finger_threshold(base)
                print(f"  No-finger IR level ~{int(base)}, finger threshold set to {int(finger_thr)}.")
                print("  (Check it on your hardware with --finger-test.)")
    detector = FingerDetector(finger_thr)

    logger = Logger(args.log, args.est_log) if (args.log or args.est_log) else None
    if logger:
        print("Logging:", ", ".join(p for p in (args.log, args.est_log) if p))
    print("Place a fingertip on the sensor and hold still. Ctrl+C to stop.\n")

    red_buf, ir_buf = deque(maxlen=WINDOW_MAX), deque(maxlen=WINDOW_MAX)
    recent_ir, recent_red = deque(maxlen=50), deque(maxlen=50)
    hr_hist, sp_hist = deque(maxlen=5), deque(maxlen=5)
    seq = 0                     # samples actually received
    sensor_idx = 0              # position on the sensor's own timeline (includes dropped samples)
    pending_gap_est = 0
    pending_gap_hw = 0
    events = []
    skip = 0
    was_present = False
    overflow_events = 0
    lost_total_est = 0
    errors = 0
    last_est = 0.0
    last_led_change = 0.0
    t_read_prev = None
    t_start = time.monotonic()

    def reset_window():
        red_buf.clear()
        ir_buf.clear()
        hr_hist.clear()
        sp_hist.clear()

    def handle(samples, t_read, t_wall, lost):
        nonlocal seq, sensor_idx, pending_gap_est, pending_gap_hw, skip, was_present
        nonlocal overflow_events, lost_total_est, t_read_prev
        for red, ir in samples:
            gap_est = gap_hw = 0
            if pending_gap_est or pending_gap_hw:      # samples were dropped just before this one
                gap_est, gap_hw = pending_gap_est, pending_gap_hw
                pending_gap_est = pending_gap_hw = 0
                sensor_idx += gap_est
                reset_window()
                skip = max(skip, FS // 2)
                events.append("overflow")
            seq += 1
            sensor_idx += 1
            recent_ir.append(ir)
            recent_red.append(red)
            present = detector.update(sum(recent_ir) / len(recent_ir))
            if present != was_present:                 # finger placed or removed
                reset_window()
                skip = FS if present else 0            # ignore the touch transient
                was_present = present
                events.append("finger_on" if present else "finger_off")
            if logger and logger.raw:
                logger.raw.writerow([seq, f"{sensor_idx / FS:.3f}", f"{t_read - t_start:.4f}",
                                     f"{t_wall:.3f}", red, ir, int(present), led,
                                     gap_est, gap_hw, "|".join(events)])
            events.clear()
            if present:
                if skip > 0:
                    skip -= 1
                else:
                    red_buf.append(red)
                    ir_buf.append(ir)
        if lost:
            # The FIFO keeps the OLDEST 32 samples and drops NEWER ones, so the gap lies
            # after this burst. The hardware counter stops at 15; estimate the real number
            # from the host clock (samples produced since the last read, minus those kept).
            overflow_events += 1
            est = lost
            if t_read_prev is not None:
                est = max(lost, int(round((t_read - t_read_prev) * FS)) - len(samples))
            pending_gap_est += est
            pending_gap_hw += lost
            lost_total_est += est
            print(f"WARNING: FIFO overflow. Hardware counter >= {lost}, ~{est} samples estimated "
                  f"lost (loop too slow). Analysis window will restart.")
        t_read_prev = t_read

    try:
        while True:
            try:
                samples, lost = sensor.read_samples()
                t_read, t_wall = time.monotonic(), time.time()
                errors = 0
            except OSError as e:
                errors += 1
                if errors >= 5:
                    print(f"I2C keeps failing ({e}). Check wiring/contact.")
                    return 1
                time.sleep(0.05)
                continue
            handle(samples, t_read, t_wall, lost)

            now = time.monotonic()
            if now - last_est >= 1.0 and recent_ir:
                last_est = now
                present = detector.present
                saturated = max(max(recent_ir), max(recent_red)) >= SATURATION

                settled = present and skip == 0 and len(ir_buf) >= FS   # >= 1 s of stable data
                if settled and not args.no_auto_led and now - last_led_change > 3.0:
                    tail_ir = sum(list(ir_buf)[-FS:]) / FS
                    new_led = led
                    if saturated and led > LED_MIN:
                        new_led = max(LED_MIN, int(led * 0.75))
                    elif tail_ir < 40000 and led < LED_MAX_AUTO:
                        new_led = min(LED_MAX_AUTO, int(led * 1.25) + 1)
                    if new_led != led:
                        # Drain samples already acquired with the OLD current so they are
                        # logged with the correct LED value, then switch.
                        s2, l2 = sensor.read_samples()
                        handle(s2, time.monotonic(), time.time(), l2)
                        led = new_led
                        sensor.set_led(led)
                        events.append("led_change")
                        last_led_change = now
                        reset_window()
                        skip = FS
                        print(f"(LED current adjusted to 0x{led:02X} ~{led * 0.2:.1f} mA because "
                              f"signal was {'saturated' if saturated else 'weak'})")

                red_now, ir_now = recent_red[-1], recent_ir[-1]
                if not present:
                    msg = "Place your finger on the sensor" if args.simple else \
                          f"raw red={red_now:6d} ir={ir_now:6d} | no finger detected"
                elif len(ir_buf) < WINDOW_MIN:
                    msg = "Measuring... keep your finger still" if args.simple else \
                          f"raw red={red_now:6d} ir={ir_now:6d} | collecting {len(ir_buf)}/{WINDOW_MIN}"
                else:
                    res = analyze(list(red_buf), list(ir_buf), args.spo2_coeffs)
                    if res["hr"] is not None:
                        hr_hist.append(res["hr"])
                    if res["spo2"] is not None:
                        sp_hist.append(res["spo2"])
                    hr_s = median(hr_hist) if hr_hist and res["hr"] is not None else None
                    sp_s = median(sp_hist) if sp_hist and res["spo2"] is not None else None
                    if args.simple:
                        msg = (f"BPM: {hr_s:.0f}   SpO2: {sp_s:.0f}%" if hr_s and sp_s
                               else "Signal unclear... keep your finger still")
                    else:
                        pi_txt = f"{res['pi']:.2f}%" if res["pi"] is not None else "--"
                        msg = f"raw red={red_now:6d} ir={ir_now:6d} | "
                        msg += f"HR {hr_s:5.1f} bpm" if hr_s else "HR   -- bpm"
                        msg += f" | SpO2 {sp_s:5.1f} %" if sp_s else " | SpO2  -- %"
                        msg += f" | PI {pi_txt} | {res['quality']}"
                        if saturated:
                            msg += " | SATURATED"
                    if logger and logger.est:
                        f2 = lambda v, n=2: "" if v is None else f"{v:.{n}f}"
                        logger.est.writerow([seq, f"{sensor_idx / FS:.3f}", f2(res["hr"]),
                                             f2(res["spo2"]), f2(hr_s), f2(sp_s), f2(res["r"], 4),
                                             f2(res["corr"], 3), f2(res["pi"], 3),
                                             res["quality"], 1, led])
                print(msg)
                if logger:
                    logger.flush()

            if args.seconds and now - t_start >= args.seconds:
                break
            time.sleep(0.03)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        elapsed = max(time.monotonic() - t_start, 1e-9)
        print(f"\nReceived {seq} samples in {elapsed:.1f} s ({seq / elapsed:.1f} Hz, expected {FS}); "
              f"FIFO overflow events: {overflow_events}"
              + (f", ~{lost_total_est} samples estimated lost" if overflow_events else ""))
        if logger:
            logger.close()
    return 0


def main():
    p = argparse.ArgumentParser(description="MAX30102 reader")
    p.add_argument("--bus", type=int, default=1, help="I2C bus (default 1 = pins 3/5)")
    p.add_argument("--addr", type=lambda x: int(x, 0), default=DEFAULT_ADDR, help="I2C address (0x57)")
    p.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = forever)")
    p.add_argument("--check", action="store_true", help="only detect the chip and print IDs")
    p.add_argument("--finger-test", action="store_true",
                   help="measure no-finger vs finger IR levels and validate the finger threshold")
    p.add_argument("--simple", action="store_true", help="print only BPM and SpO2")
    p.add_argument("--led", type=lambda x: int(x, 0), default=0x3F,
                   help="LED current register value, 0.2 mA per step (default 0x3F ~12.6 mA)")
    p.add_argument("--no-auto-led", action="store_true", help="do not adjust LED current automatically")
    p.add_argument("--finger-min", type=float, default=None,
                   help="fixed IR level that counts as 'finger present' (skips calibration)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="skip the no-finger baseline and use the default threshold")
    p.add_argument("--spo2-coeffs", type=float, nargs=3, metavar=("A", "B", "C"),
                   default=DEFAULT_SPO2_COEFFS, help="SpO2 = A*R^2 + B*R + C")
    p.add_argument("--log", nargs="?", const="auto", default=None, metavar="FILE",
                   help="log every raw sample to CSV (default name is timestamped)")
    p.add_argument("--est-log", nargs="?", const="auto", default=None, metavar="FILE",
                   help="log the once-per-second estimates to CSV")
    args = p.parse_args()
    if args.log == "auto":
        args.log = auto_name("raw")
    if args.est_log == "auto":
        args.est_log = auto_name("est")

    try:
        sensor = MAX30102(args.bus, args.addr)
    except (PermissionError, FileNotFoundError) as e:
        print(f"Cannot open bus {args.bus}: {e} -> try sudo")
        return 1
    try:
        if args.check:
            return check_only(sensor, args)
        if args.finger_test:
            return finger_test(sensor, args)
        return run(sensor, args)
    except OSError as e:
        print(f"I2C error: {e}")
        return 1
    finally:
        sensor.close()


if __name__ == "__main__":
    sys.exit(main())
