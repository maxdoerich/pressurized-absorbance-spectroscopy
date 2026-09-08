#!/usr/bin/env python3
"""Plot the Biowave-II absorbance time series from a photometer_capture.py CSV.

Usage:
    python3 plot_photometer.py data/photometer/photometer-<stamp>.csv
    python3 plot_photometer.py data/photometer/photometer-<stamp>.csv --itv data/itv-<stamp>.csv
    python3 plot_photometer.py <csv> --itv <itv-csv> --offset 27 --out /path/out.png --title "..."

Reads the parsed CSV (time,label,value). For a Kinetics run `label` is the point
index (1..N) and `value` the absorbance; `time` carries the *nominal* interval
labels (00:00:00, 00:00:05, ...). CAREFUL: the Biowave does NOT fold the ~3.2 s
measurement time into the interval, so a nominal 5 s Kinetics really samples every
~8.16 s and a nominal "5 min" run spans ~8.2 min. 8.16 s is the value confirmed
in the live sync test (s. Testprotokoll "Live-Synchronisationstest ... Schrittweite
8,16s bestaetigt", 2026-08-24; the earlier theoretical estimate was ~8.19 s). For
anything time-critical -- above all overlaying the pressure sweep -- pass the
measured spacing with --interval 8.16 instead of trusting the nominal labels.

With --itv, the paired pressure sweep (capture.py CSV) is overlaid on a second
y-axis as Ist-Druck (bar), using the same ITV0050 calibration as plot_sweep.py.
Both series are assumed to start together; --offset <s> shifts the ITV trace
(positive = ITV started later than the photometer, so it moves left).

Default output: assets/Hydrostatic-Pressure-Setup/sweeps/photometer_<csv-stem>.png
(Vault-Root, relativ zu diesem Skript).
"""
import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

# ITV0050 calibration -- must match capture.py / plot_sweep.py.
P_FULL_BAR = 9.0
MONITOR_V_ZERO = 1.0
MONITOR_V_MAX = 5.0

VAULT_ROOT = Path(__file__).resolve().parents[3]


def ist_bar(v):
    return (v - MONITOR_V_ZERO) / (MONITOR_V_MAX - MONITOR_V_ZERO) * P_FULL_BAR


def parse_hms(s):
    """'hh:mm:ss' -> seconds; None if it does not parse."""
    parts = s.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, sec = (int(p) for p in parts)
    except ValueError:
        return None
    return h * 3600 + m * 60 + sec


def leading_kinetics(rows):
    """Return just the first Kinetics series.

    photometer_capture.py keeps appending to one CSV while it runs, so a file can
    hold a Kinetics series (time 00:00:00 < 00:00:05 < ...) followed by later
    Single-Wavelength readings (stuck 00:01:20 clock, label resets). Keep the
    leading run of strictly increasing timestamps; fall back to all rows (e.g. a
    pure Single-Wavelength file) if that yields too little.
    """
    out, prev = [], -1
    for r in rows:
        sec = parse_hms(r["time"])
        if sec is None or sec <= prev:
            break
        out.append(r)
        prev = sec
    return out if len(out) >= 3 else rows


def load_photometer(path, interval=None, skip=0):
    """-> (t_seconds, absorbance).

    interval given -> t = index * interval (use the *measured* ~8.16 s spacing).
    interval None  -> parse the nominal hh:mm:ss labels, falling back to index*5s.
    skip N -> drop the first N points (e.g. Blasen-Artefakte beim Anfahren), but
    keep the *absolute* time position of the rest so an --itv overlay stays aligned.
    """
    rows = leading_kinetics(list(csv.DictReader(open(path))))
    if not rows:
        raise SystemExit(f"Keine Daten in {path}")
    a = [float(r["value"]) for r in rows]
    if interval:
        t = [i * interval for i in range(len(rows))]
    else:
        t = [parse_hms(r["time"]) for r in rows]
        if any(x is None for x in t) or len(set(t)) < len(t) // 2:
            t = [i * 5.0 for i in range(len(rows))]  # nominal 5 s interval
    if skip:
        t, a = t[skip:], a[skip:]
    return t, a


def load_itv(path):
    rows = list(csv.DictReader(open(path)))
    if not rows:
        raise SystemExit(f"Keine Daten in {path}")
    t = [float(r["t_s"]) for r in rows]
    ist = [ist_bar(float(r["monitor_v"])) for r in rows]
    return t, ist


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="photometer_capture.py-CSV (time,label,value)")
    ap.add_argument("--itv", type=Path, default=None,
                    help="gepaarte capture.py-Druck-CSV, als zweite Achse (Ist-Druck bar)")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="Zeitversatz des ITV-Logs in s (positiv = ITV spaeter gestartet)")
    ap.add_argument("--interval", type=float, default=None, metavar="SEC",
                    help="gemessenes Punktintervall statt der nominellen Labels "
                         "(Biowave 5-s-Kinetik = real ~8.16 s, im Live-Sync bestaetigt)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output-PNG (Default: assets/Hydrostatic-Pressure-Setup/sweeps/photometer_<stem>.png)")
    ap.add_argument("--title", default=None, help="eigener Plot-Titel")
    ap.add_argument("--ylim", type=float, nargs=2, default=None, metavar=("LO", "HI"),
                    help="feste A-Achse (z. B. -0.05 0.9), sonst Autoskala")
    ap.add_argument("--skip", type=int, default=0, metavar="N",
                    help="erste N Messpunkte weglassen (Blasen-Artefakte beim Anfahren); "
                         "Zeitachse der restlichen Punkte bleibt absolut, --itv bleibt ausgerichtet")
    args = ap.parse_args()

    t_a, a = load_photometer(args.csv, args.interval, args.skip)
    t_min = [x / 60.0 for x in t_a]

    suffix = "_itv" if args.itv else ""
    out = args.out or (VAULT_ROOT / "assets" / "Hydrostatic-Pressure-Setup"
                       / "sweeps" / f"photometer_{args.csv.stem}{suffix}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    ax.plot(t_min, a, marker="o", ms=3, lw=1.4, color="#1f77b4",
            label="A (Biowave II, 500 nm)")
    ax.set_xlabel("Zeit (min)")
    ax.set_ylabel("Absorption A")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(min(t_min) if t_min else 0, max(t_min) if t_min else 1)
    if args.ylim:
        ax.set_ylim(*args.ylim)

    if args.itv:
        t_i, ist = load_itv(args.itv)
        t_i_min = [(x - args.offset) / 60.0 for x in t_i]
        ax2 = ax.twinx()
        ax2.plot(t_i_min, ist, lw=1.0, color="#d62728", alpha=0.8,
                 label="Ist-Druck (ITV-Monitor)")
        ax2.set_ylabel("Druck (bar)")
        lines = ax.get_lines() + ax2.get_lines()
        ax.legend(lines, [ln.get_label() for ln in lines], loc="best")
    else:
        ax.legend(loc="best")

    if args.title:
        title = args.title
    elif args.itv:
        title = f"{args.csv.name}  +  {Path(args.itv).name}"
    else:
        title = args.csv.name
    ax.set_title(title)

    fig.tight_layout()
    fig.savefig(out)
    print(f"gespeichert: {out}")


if __name__ == "__main__":
    main()
