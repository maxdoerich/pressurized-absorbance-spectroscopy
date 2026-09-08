#!/usr/bin/env python3
"""Log the WPA Biowave II "print" stream to a raw file + a parsed CSV.

The Biowave II has no remote control -- with "Auto-Print" on it emits data over
its USB Type-B port as ASCII. Serial params are fixed: 115200 8N1, no handshake
(found empirically 2026-09-01, see Testprotokoll). The instrument speaks WPA's
"Print via Computer" protocol: every run starts with a header dump (product /
serial no / wavelength / mode / column defs), all lines ending ' 0'. The trailing
number on a "$?C" line is a type code -- **1024 marks a real data value**, 0 (or
a small column width) marks header/metadata.

Two data layouts, both handled here:

* Single Wavelength -- one block per reading:
      $PCT
      $PC "00:01:20" 0     instrument clock (usually unset -> ignore)
      $PC "Reference" 0    label: "Reference" or a reading number (" 27")
      $PC "0.199" 1024     the value
      $PET
  -> CSV row: <clock>,<label>,<value>

* Kinetics -- dumped at end of run; the time series is the $XC pair block that
  follows "$XCD \"TN\"":
      $XC "00:00:05" 1024  elapsed time hh:mm:ss
      $XC "-0.002"  1024   absorbance at that time
      $XUR
  -> CSV row: <elapsed>,<point #>,<value>

Each invocation writes two timestamped files into data/photometer/:
    photometer-<stamp>.txt   raw protocol, lossless (the authoritative record)
    photometer-<stamp>.csv   parsed: time,label,value  (best effort)

Stdlib only -- no pyserial. Ctrl-C to stop.
"""
import glob
import os
import re
import select
import sys
import termios
from datetime import datetime

BAUD = "115200"

# Single Wavelength: per-reading $PC block.
CLOCK_RE = re.compile(r'^\$PC "(\d{2}:\d{2}:\d{2})" \d+$')
LABEL_RE = re.compile(r'^\$PC "(.+?)" 0$')
VALUE_RE = re.compile(r'^\$PC "(-?\d+(?:\.\d+)?)" 1024$')      # 1024 = real reading

# Kinetics: $XC "hh:mm:ss" 1024 / $XC "<value>" 1024 pairs in the series block.
XTIME_RE = re.compile(r'^\$XC "(\d{2}:\d{2}:\d{2})" 1024$')
XVALUE_RE = re.compile(r'^\$XC "(-?\d+(?:\.\d+)?)" 1024$')


def set_raw(fd, baud):
    """8N1 raw mode at `baud`, applied to an already-open fd.

    macOS reverts a `stty -f` call when it closes the port, so the baud rate
    MUST be set on the open fd or the next read is garbage (see capture.py).
    """
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


def find_port(argv):
    if len(argv) > 1:
        return argv[1]
    ports = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/cu.usbmodem*"))
    if not ports:
        sys.exit("No USB-serial port found. Photometer on and plugged in? "
                 "Pass one explicitly: photometer_capture.py /dev/cu.XXXX")
    if len(ports) > 1:
        sys.exit(f"Multiple ports found, pick one: {' '.join(ports)}")
    return ports[0]


def main():
    port = find_port(sys.argv)
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "photometer")
    os.makedirs(outdir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_path = os.path.join(outdir, f"photometer-{stamp}.txt")
    csv_path = os.path.join(outdir, f"photometer-{stamp}.csv")

    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    set_raw(fd, BAUD)

    raw = open(raw_path, "w", buffering=1)
    csv = open(csv_path, "w", buffering=1)
    csv.write("time,label,value\n")

    print(f"[capture] {port} @ {BAUD} 8N1")
    print(f"[capture] raw -> {raw_path}")
    print(f"[capture] csv -> {csv_path}")
    print("[capture] start a measurement / kinetics run on the Biowave. "
          "For Kinetics, let the run finish so the series is printed. "
          "Ctrl-C to stop.\n")

    buf = b""
    clock, label, rows = "", "", 0
    kin_time, kin_n = None, 0          # pending $XC time, kinetics point counter
    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if fd not in ready:
                continue
            buf += os.read(fd, 4096)
            while b"\n" in buf:
                chunk, buf = buf.split(b"\n", 1)
                line = chunk.decode("ascii", "replace").strip()
                if not line:
                    continue
                raw.write(line + "\n")

                # --- Kinetics series: $XC "time" 1024 / $XC "value" 1024 ---
                m = XTIME_RE.match(line)
                if m:
                    kin_time = m.group(1)
                    continue
                m = XVALUE_RE.match(line)
                if m and kin_time is not None:
                    kin_n += 1
                    csv.write(f"{kin_time},{kin_n},{m.group(1)}\n")
                    rows += 1
                    print(f"\r[{kin_time}]  kin #{kin_n:<4d} =  {m.group(1)}",
                          flush=True)
                    kin_time = None
                    continue

                # --- Single Wavelength: per-reading $PC block ---
                if line == "$PCT":            # start of a reading block
                    label = ""
                    continue
                m = CLOCK_RE.match(line)
                if m:
                    clock = m.group(1)
                    continue
                m = VALUE_RE.match(line)
                if m:
                    value = m.group(1)
                    csv.write(f"{clock},{label},{value}\n")
                    rows += 1
                    tag = label if label else "?"
                    print(f"\r[{clock}]  {tag:>10s}  =  {value}", flush=True)
                    label = ""
                    continue
                m = LABEL_RE.match(line)
                if m:
                    label = m.group(1).strip()
    except KeyboardInterrupt:
        pass
    finally:
        raw.close()
        csv.close()
        os.close(fd)
        print(f"\n[capture] done. {rows} readings -> {csv_path}")
        if rows == 0:
            print("[capture] no readings parsed -- check data/photometer/"
                  f"photometer-{stamp}.txt for the raw stream.")


if __name__ == "__main__":
    main()
