#!/usr/bin/env python3
"""Plot Biowave-II-Absorption direkt gegen den Ist-Druck (ITV-Monitor).

Statt zweier Zeitreihen (s. plot_photometer.py) wird hier A gegen den *pro
Kinetik-Intervall gemittelten* Ist-Druck aufgetragen -- die Kollaps-Kennlinie.

Fuer jeden Photometer-Punkt i (nach --skip) wird das Zeitfenster
[t_i, t_i + interval) in Photometerzeit gebildet und der Mittelwert aller
ITV-Monitor-Druckwerte in diesem Fenster genommen (ITV-Zeit = t_s - offset,
gleiche Konvention wie plot_photometer.py).

WICHTIG:
  * Biowave-"5 s"-Kinetik sampelt real laenger. Als Standard-Schrittweite gilt
    8.16 s -- der empirisch im Live-Sync-Test bestaetigte Wert (s. Testprotokoll
    "Live-Synchronisationstest ... Schrittweite 8,16s bestaetigt", 2026-08-24;
    die theoretische Schaetzung war ~8.19 s). Default hier ist 8.16; nur bei
    abweichender Sweep-Haltezeit --interval anpassen.
  * Das capture.py-ITV-Log endet, sobald der Sweep durch ist; danach faellt der
    Druck auf Atmosphaerendruck. Photometer-Punkte, deren Fenster komplett hinter
    dem ITV-Log liegen, werden als 0 bar (drucklos) gefuehrt -- mit --drop-uncovered
    stattdessen weggelassen.

Usage:
    python3 plot_od_vs_pressure.py data/photometer/photometer-<stamp>.csv \
        --itv data/itv-<stamp>.csv --offset 18 --skip 6
    python3 plot_od_vs_pressure.py <phot-csv> --itv <itv-csv> \
        --drop-uncovered --out /pfad/out.png --title "..."

Default-Output: assets/Hydrostatic-Pressure-Setup/sweeps/od_vs_druck_<phot-stem>.png
"""
import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

# ITV0050 calibration -- must match capture.py / plot_sweep.py / plot_photometer.py.
P_FULL_BAR = 9.0
MONITOR_V_ZERO = 1.0
MONITOR_V_MAX = 5.0

VAULT_ROOT = Path(__file__).resolve().parents[3]


def ist_bar(v):
    return (v - MONITOR_V_ZERO) / (MONITOR_V_MAX - MONITOR_V_ZERO) * P_FULL_BAR


def parse_hms(s):
    parts = s.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, sec = (int(p) for p in parts)
    except ValueError:
        return None
    return h * 3600 + m * 60 + sec


def leading_kinetics(rows):
    """Erste Kinetics-Serie (streng steigende Zeitstempel) -- Rest (spaetere
    Single-Wavelength-Messungen mit eingefrorener Uhr) abschneiden."""
    out, prev = [], -1
    for r in rows:
        sec = parse_hms(r["time"])
        if sec is None or sec <= prev:
            break
        out.append(r)
        prev = sec
    return out if len(out) >= 3 else rows


def load_photometer(path, interval, skip):
    rows = leading_kinetics(list(csv.DictReader(open(path))))
    if not rows:
        raise SystemExit(f"Keine Daten in {path}")
    a = [float(r["value"]) for r in rows]
    t = [i * interval for i in range(len(rows))]
    return t[skip:], a[skip:]


def load_itv(path, offset):
    rows = list(csv.DictReader(open(path)))
    if not rows:
        raise SystemExit(f"Keine Daten in {path}")
    # ITV-Zeit auf Photometer-Zeitbasis bringen
    t = [float(r["t_s"]) - offset for r in rows]
    bar = [ist_bar(float(r["monitor_v"])) for r in rows]
    return t, bar


def mean_pressure_per_interval(t_phot, interval, t_itv, bar_itv, drop_uncovered):
    """-> (kept_indices, pressures) -- pro Photometer-Fenster gemittelter Ist-Druck.

    Fenster ohne ITV-Deckung: 0 bar (Atmosphaere), sofern nach dem ITV-Log-Ende;
    mit drop_uncovered=True stattdessen ausgelassen.
    """
    itv_end = max(t_itv)
    pairs = sorted(zip(t_itv, bar_itv))
    ts = [p[0] for p in pairs]
    bs = [p[1] for p in pairs]

    kept, press = [], []
    for i, t0 in enumerate(t_phot):
        t1 = t0 + interval
        vals = [b for tt, b in zip(ts, bs) if t0 <= tt < t1]
        if vals:
            press.append(sum(vals) / len(vals))
            kept.append(i)
        elif t0 >= itv_end and not drop_uncovered:
            press.append(0.0)          # Sweep vorbei -> Atmosphaerendruck
            kept.append(i)
        # sonst: Fenster ausserhalb jeder Deckung -> weglassen
    return kept, press


def _interp_crossing(xs, ys, y_target):
    """Erste lineare Kreuzung von y_target in (xs, ys) -- oder None."""
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if (y0 - y_target) * (y1 - y_target) <= 0 and y0 != y1:
            f = (y_target - y0) / (y1 - y0)
            return x0 + f * (x1 - x0)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="photometer_capture.py-CSV (time,label,value)")
    ap.add_argument("--itv", type=Path, required=True,
                    help="gepaarte capture.py-Druck-CSV (t_s,dir,soll_v,loopback_v,monitor_v)")
    ap.add_argument("--interval", type=float, default=8.16, metavar="SEC",
                    help="Punktintervall in s (Default 8.16 = im Live-Sync-Test bestaetigte "
                         "Biowave-5-s-Kinetik-Schrittweite; theoret. Schaetzung war ~8.19)")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="Zeitversatz des ITV-Logs in s (positiv = ITV spaeter gestartet)")
    ap.add_argument("--skip", type=int, default=0, metavar="N",
                    help="erste N Photometer-Punkte weglassen (Blasen-Artefakte beim Anfahren)")
    ap.add_argument("--drop-uncovered", action="store_true",
                    help="Punkte hinter dem ITV-Log-Ende weglassen statt als 0 bar zu fuehren")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output-PNG (Default: assets/Hydrostatic-Pressure-Setup/sweeps/od_vs_druck_<stem>.png)")
    ap.add_argument("--title", default=None, help="eigener Plot-Titel")
    ap.add_argument("--ylim", type=float, nargs=2, default=None, metavar=("LO", "HI"),
                    help="feste A-Achse, sonst Autoskala")
    args = ap.parse_args()

    t_phot, a = load_photometer(args.csv, args.interval, args.skip)
    t_itv, bar_itv = load_itv(args.itv, args.offset)

    kept, press = mean_pressure_per_interval(
        t_phot, args.interval, t_itv, bar_itv, args.drop_uncovered)
    if len(kept) < 2:
        raise SystemExit("Zu wenig ueberlappende Datenpunkte.")
    a_k = [a[i] for i in kept]
    t_k_min = [t_phot[i] / 60.0 for i in kept]
    n_atm = sum(1 for i, p in zip(kept, press) if p == 0.0 and t_phot[i] >= max(t_itv))

    # --- Kennzahlen -----------------------------------------------------------
    baseline = sum(a_k[:5]) / len(a_k[:5])
    plateau = sum(a_k[-5:]) / len(a_k[-5:])
    a_min = min(a_k)
    # Kollaps-Kennlinie nur ueber den Hochramp-Teil (Druck monoton steigend)
    up = [(p, y) for p, y in zip(press, a_k) if p > 0.05]
    up.sort()
    xs, ys = [p for p, _ in up], [y for _, y in up]
    p_onset = _interp_crossing(xs, ys, baseline * 0.95)
    p50 = _interp_crossing(xs, ys, (baseline + plateau) / 2.0)

    print(f"Punkte gesamt (nach --skip): {len(t_phot)}  |  im Plot: {len(kept)}"
          f"  |  davon drucklos (nach Sweep-Ende): {n_atm}")
    print(f"Baseline A (erste 5):      {baseline:.3f}")
    print(f"Plateau  A (letzte 5):     {plateau:.3f}   -> Netto-Abfall {(baseline-plateau)/baseline*100:.1f} %")
    print(f"Minimum  A:                {a_min:.3f}      -> transient {(baseline-a_min)/baseline*100:.1f} %")
    if p_onset:
        print(f"Kollaps-Onset (A = 95 % Baseline):  ~{p_onset:.2f} bar")
    if p50:
        print(f"Halbkollaps-Druck P50 (A = Mitte Baseline/Plateau): ~{p50:.2f} bar")

    # --- Plot ---------------------------------------------------------------
    out = args.out or (VAULT_ROOT / "assets" / "Hydrostatic-Pressure-Setup"
                       / "sweeps" / f"od_vs_druck_{args.csv.stem}.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
    # Verbindungslinie nur durch die Punkte unter Druck (Hochrampe) --
    # der Sprung zu den drucklosen Nach-Sweep-Punkten wird nicht gezogen.
    seg_p = [p if p > 0.05 else float("nan") for p in press]
    ax.plot(seg_p, a_k, lw=0.8, color="#999999", zorder=1)
    sc = ax.scatter(press, a_k, c=t_k_min, cmap="viridis", s=32, zorder=2,
                    edgecolor="white", linewidth=0.4)
    atm = [(p, y) for p, y in zip(press, a_k) if p <= 0.05]
    if atm:
        ax.scatter([p for p, _ in atm], [y for _, y in atm], s=34,
                   facecolor="none", edgecolor="#666666", linewidth=1.0, zorder=2)
    ax.scatter([press[0]], [a_k[0]], marker="s", s=90, facecolor="none",
               edgecolor="#1f77b4", linewidth=1.8, zorder=3, label="Start")
    if p50:
        ax.axvline(p50, ls="--", lw=1.0, color="#d62728", alpha=0.7,
                   label=f"P50 ~ {p50:.1f} bar")
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("Zeit seit Kinetik-Start (min)")
    ax.set_xlabel("Ist-Druck (ITV-Monitor), pro Kinetik-Intervall gemittelt  [bar]")
    ax.set_ylabel("Absorption A (Biowave II, 500 nm)")
    ax.grid(True, alpha=0.3)
    if args.ylim:
        ax.set_ylim(*args.ylim)
    ax.set_title(args.title or f"OD vs. Druck  --  {args.csv.name}")
    if n_atm:
        ax.text(0.02, 0.02,
                f"{n_atm} Punkte bei 0 bar = nach Sweep-Ende, Druck abgelassen",
                transform=ax.transAxes, fontsize=8, color="#555555")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out)
    print(f"gespeichert: {out}")


if __name__ == "__main__":
    main()
