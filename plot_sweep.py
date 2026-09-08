#!/usr/bin/env python3
"""Plot Solldruck vs. Ist-Druck (ITV-Monitor) from a capture.py sweep CSV.

Usage:
    python3 plot_sweep.py data/itv-<timestamp>.csv
    python3 plot_sweep.py data/itv-<timestamp>.csv --out /path/to/output.png
    python3 plot_sweep.py data/itv-<timestamp>.csv --title "Eigener Titel"

Default output: assets/Hydrostatic-Pressure-Setup/sweeps/druckverlauf_<csv-stem>.png (Vault-Root, relativ zu diesem Skript).
Kalibrierkonstanten identisch zu capture.py (s. dort für Details/Quelle).
"""
import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

# ITV0050 calibration -- must match capture.py.
P_FULL_BAR = 9.0
SETPOINT_V_MAX = 5.0
MONITOR_V_ZERO = 1.0
MONITOR_V_MAX = 5.0

VAULT_ROOT = Path(__file__).resolve().parents[3]


def soll_bar(v):
    return v / SETPOINT_V_MAX * P_FULL_BAR


def ist_bar(v):
    return (v - MONITOR_V_ZERO) / (MONITOR_V_MAX - MONITOR_V_ZERO) * P_FULL_BAR


def detect_step_hold(rows):
    """Grobe Schaetzung von Schrittgroesse (V) und Haltezeit (s) aus den Daten."""
    steps = []
    prev = None
    for r in rows:
        key = (r["dir"], r["soll_v"])
        if key != prev:
            steps.append(float(r["t_s"]))
            prev = key
    if len(steps) < 3:
        return None, None
    hold = steps[2] - steps[1]  # skip the first (often shorter/aborted) step
    soll_vals = sorted({float(r["soll_v"]) for r in rows})
    step_size = None
    if len(soll_vals) > 1:
        diffs = [round(b - a, 3) for a, b in zip(soll_vals, soll_vals[1:])]
        step_size = min(diffs)
    return step_size, hold


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", type=Path, help="Pfad zur capture.py-CSV (t_s,dir,soll_v,loopback_v,monitor_v)")
    ap.add_argument("--out", type=Path, default=None, help="Output-PNG-Pfad (Default: assets/Hydrostatic-Pressure-Setup/sweeps/druckverlauf_<csv-stem>.png)")
    ap.add_argument("--title", default=None, help="Eigener Plot-Titel statt der automatisch erkannten Schritt-/Haltezeit-Angabe")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv)))
    if not rows:
        raise SystemExit(f"Keine Daten in {args.csv}")

    t = [float(r["t_s"]) / 60.0 for r in rows]  # Minuten
    soll = [soll_bar(float(r["soll_v"])) for r in rows]
    ist = [ist_bar(float(r["monitor_v"])) for r in rows]

    out = args.out or (VAULT_ROOT / "assets" / "Hydrostatic-Pressure-Setup" / "sweeps" / f"druckverlauf_{args.csv.stem}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.title:
        title = args.title
    else:
        step_size, hold = detect_step_hold(rows)
        if step_size and hold:
            title = f"{step_size:.2f}V-Stufensweep, {hold:.1f}s Haltezeit/Stufe\n{args.csv.name}"
        else:
            title = args.csv.name

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    ax.plot(t, soll, label="Solldruck (DAC-Vorgabe)", color="#1f77b4", linewidth=1.6)
    ax.plot(t, ist, label="Ist-Druck (ITV-Monitor)", color="#d62728", linewidth=1.0, alpha=0.85)
    ax.set_xlabel("Zeit (min)")
    ax.set_ylabel("Druck (bar)")
    ax.set_title(title)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, max(t))
    fig.tight_layout()
    fig.savefig(out)
    print(f"gespeichert: {out}")


if __name__ == "__main__":
    main()
