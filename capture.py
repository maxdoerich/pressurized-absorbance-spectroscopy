#!/usr/bin/env python3
"""Log an ITV0050 Nano sketch's serial output to CSV while staying interactive.

Prompts and status lines from the sketch go to the terminal only; CSV rows go to
both. Each header line the sketch prints ("t_s,...") opens a new file, so one
sweep = one CSV. Stdlib only -- no pyserial. Ctrl-C to stop.
"""
import glob
import os
import re
import select
import sys
import termios
import tty
from datetime import datetime

BAUD = "115200"

# ITV0050 calibration (see Hydrostatic-Pressure-Chamber.md).
# Setpoint: 0-5 V spans 0-9 bar.  Monitor echo: 1-5 V spans 0-9 bar.
P_FULL_BAR = 9.0          # 0.9 MPa
SETPOINT_V_MAX = 5.0
MONITOR_V_ZERO = 1.0      # monitor output at zero pressure
MONITOR_V_MAX = 5.0

HEADER_RE = re.compile(r"^t_s,[a-z_,]+$")
DATA_RE = re.compile(r"^[0-9]")


def set_raw(fd, baud):
    """8N1 raw mode at `baud`, applied to an already-open fd."""
    speed = getattr(termios, f"B{baud}")
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(fd)
    iflag &= ~(termios.IXON | termios.IXOFF | termios.IXANY | termios.ICRNL
               | termios.INLCR | termios.IGNCR | termios.ISTRIP | termios.BRKINT)
    oflag &= ~termios.OPOST
    lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG
               | termios.IEXTEN)
    cflag &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    cflag |= termios.CS8 | termios.CLOCAL | termios.CREAD
    cc[termios.VMIN], cc[termios.VTIME] = 1, 0
    termios.tcsetattr(fd, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, speed, speed, cc])
    termios.tcflush(fd, termios.TCIFLUSH)     # drop any garbage already buffered


def soll_bar(v):
    return v / SETPOINT_V_MAX * P_FULL_BAR


def ist_bar(v):
    return (v - MONITOR_V_ZERO) / (MONITOR_V_MAX - MONITOR_V_ZERO) * P_FULL_BAR


def format_row(cols, line):
    """Render one CSV row as a labelled, unit-carrying status line."""
    vals = dict(zip(cols, line.split(",")))
    try:
        t = float(vals["t_s"])
        sv = float(vals["soll_v"])
        mv = float(vals["monitor_v"])
        lv = float(vals["loopback_v"])
    except (KeyError, ValueError):
        return line                      # unknown format: show it raw
    tag = ""
    if "step_idx" in vals:
        tag = f"  step {int(vals['step_idx']):>2d}"
    elif "dir" in vals:
        tag = f"  {vals['dir']:<4s}"
    sb, ib = soll_bar(sv), ist_bar(mv)
    return (f"t {t:7.1f}s{tag}"
            f"   soll {sv:5.3f} V = {sb:5.2f} bar"
            f"   ist {mv:5.3f} V = {ib:5.2f} bar"
            f"   d {ib - sb:+5.2f} bar"
            f"   loop {lv:5.3f} V")


def find_port(argv):
    if len(argv) > 1:
        return argv[1]
    ports = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        sys.exit("No Arduino-like port found. Pass one explicitly: capture.py /dev/cu.XXXX")
    if len(ports) > 1:
        sys.exit(f"Multiple ports found, pick one: {' '.join(ports)}")
    return ports[0]


def main():
    port = find_port(sys.argv)
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(outdir, exist_ok=True)

    # macOS: no auto-reset on /dev/cu.*, so the running sketch is not restarted.
    # Baud MUST be set on the open fd -- a separate `stty -f` call reverts the
    # setting when it closes the port, leaving us at 9600 and reading garbage.
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    set_raw(fd, BAUD)

    csv, path, rows, cols = None, None, 0, []
    buf = b""
    stdin_fd = sys.stdin.fileno()
    saved = termios.tcgetattr(stdin_fd) if sys.stdin.isatty() else None

    print(f"[capture] {port} @ {BAUD}  ->  {outdir}/   (Ctrl-C to stop)\n")
    try:
        if saved:
            tty.setcbreak(stdin_fd)
        while True:
            ready, _, _ = select.select([fd, stdin_fd], [], [])

            if stdin_fd in ready:                      # forward keystrokes to the Nano
                ch = os.read(stdin_fd, 1024)
                if not ch:
                    break
                os.write(fd, ch.replace(b"\r", b"\n"))  # sketch reads until '\n'
                sys.stdout.write(ch.replace(b"\r", b"\n").decode("utf-8", "replace"))
                sys.stdout.flush()

            if fd in ready:
                buf += os.read(fd, 4096)
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    if HEADER_RE.match(line):          # new run -> new file
                        if csv:
                            csv.close()
                            print(f"\n[capture] wrote {rows} rows -> {path}")
                        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                        path = os.path.join(outdir, f"itv-{stamp}.csv")
                        csv, rows = open(path, "w", buffering=1), 0
                        csv.write(line + "\n")
                        cols = line.split(",")
                        print(f"[capture] logging -> {path}")
                        print(f"[capture] CSV is raw volts; bar shown below "
                              f"(setpoint 0-5 V, monitor {MONITOR_V_ZERO:g}-"
                              f"{MONITOR_V_MAX:g} V, both = 0-{P_FULL_BAR:g} bar)")
                    elif DATA_RE.match(line) and csv:
                        csv.write(line + "\n")
                        rows += 1
                        print(f"\r{format_row(cols, line)}", end="", flush=True)
                    else:
                        print(("\n" if rows else "") + line, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if saved:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, saved)
        if csv:
            csv.close()
            print(f"\n[capture] wrote {rows} rows -> {path}")
        os.close(fd)
        print("[capture] done. Note: the Nano keeps running; press its reset to force 0 V.")


if __name__ == "__main__":
    main()
