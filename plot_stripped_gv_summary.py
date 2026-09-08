#!/usr/bin/env python3
"""Zusammenfassende Abbildung fuer EINEN Hydrostatik-Sync-Lauf.

Ein Aufruf = ein Lauf (ein Photometer-Kinetics-Mitschnitt + der gepaarte
ITV-Sweep + optional die Offline-Spritzen-Kontrolle dazu). Presets:
  run1 / run2  -- Lauf E / F, gestrippte GVs ohne GvpC (2026-09-07 abends)
  laufB / laufD -- die frueheren Laeufe mit intakten purified GVs (2026-09-07 nachts)

Erzeugt eine Uebersichts-PNG mit:

  (a) Zeit vs. A500 + Ist-Druck -- ALLE Messwerte (Rohdaten, inkl. Startup-Peak)
  (b) Zeit vs. A500 + Ist-Druck -- erste --skip Punkte ausgeblendet (der clean
      Graph fuer die eigentliche Auswertung)
  (c) A500 vs. pro Kinetik-Intervall gemittelter Ist-Druck (nach --skip),
      mit Baseline/Endplateau, erwartetem Kollapsband UND -- falls es einen
      echten Abfall gibt -- der fallenden 4-Parameter-Boltzmann-Sigmoide
      (Fit nur ueber den ITV-gedeckten Hochramp-Ast, wie fit_collapse_pressure.py),
      Wendepunkt P50 = Kollapsdruck (+/- 1 sigma); rechte Achse A/A0
  (d) Spritzen-Kontrolle: Mittelwert +/- SD der Zeitpunkte nebeneinander
  (e) Netto-Prozentaenderung Setup (Baseline->Endplateau) vs. Spritze
      (vorher->spaet), mit den Referenzwerten der intakten GVs (Lauf C/D)
  (f) Kennzahlen als Text

--skip N ist der EINE Startup-Parameter: so viele der ersten Kinetik-Punkte
sind nicht Teil des clean Graphs (b) und fliessen auch nicht in Baseline/
Kollapskurve/Kennzahlen ein. Panel (a) zeigt trotzdem alles.

Beispiele:
    # bekannter Lauf ueber Preset (fuellt Dateien/skip/offset/Spritze):
    python3 plot_stripped_gv_summary.py --preset run1
    python3 plot_stripped_gv_summary.py --preset run2 --skip 8

    # beliebiger Lauf, alles explizit:
    python3 plot_stripped_gv_summary.py data/photometer/photometer-<stamp>.csv \
        --itv data/itv-<stamp>.csv --skip 6 --offset 9 \
        --syringe "0.270,0.269,0.265;0.273,0.258,0.251;0.226,0.230,0.232" \
        --syringe-labels "vorher;direkt danach;~13 min danach" \
        --label "Lauf X -- ..." --out /pfad/out.png

Default-Output: assets/Hydrostatic-Pressure-Setup/sweeps/stripped-gv_summary_<phot-stem>.png
"""
import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit

# ITV0050-Kalibrierung -- identisch zu capture.py / plot_sweep.py / plot_photometer.py.
P_FULL_BAR = 9.0
MONITOR_V_ZERO = 1.0
MONITOR_V_MAX = 5.0

# Biowave-"5 s"-Kinetik sampelt real ~8.16 s (Live-Sync-Test 2026-08-24).
INTERVAL_S = 8.16

# Erwartetes Serratia-GV-Kollapsband (s. Bacterial-GV-Expression-Overview /
# Testprotokoll: ~3.5-5.4 bar). Gestrippte GVs ohne GvpC eher noch niedriger.
COLLAPSE_BAND_BAR = (3.0, 5.4)

# ln(0.95/0.05) -- Druckabstand Wendepunkt <-> 5 %- bzw. 95 %-Kollaps, in dP
# (identisch zu fit_collapse_pressure.py).
_K_5_95 = float(np.log(0.95 / 0.05))          # ~= 2.9444
_K_10_90 = float(2.0 * np.log(9.0))           # ~= 4.3944

# Referenz: Spritzen-Kontrolle der INTAKTEN purified GVs, 2026-09-07 nachts.
REF_SYRINGE_PCT = {"Lauf C (intakt)": -37.0, "Lauf D (intakt)": -55.0}

VAULT_ROOT = Path(__file__).resolve().parents[3]
DATA = Path(__file__).resolve().parent / "data"

# --- Presets fuer die Sync-Laeufe vom 2026-09-07 ---------------------------
# offset = ITV-Log spaeter gestartet als die Kinetik (s); grob aus den
# Logger-Startzeitstempeln. Fuer die Aussage unkritisch (kein Kollaps-Feature
# zum Ausrichten), nur fuer die Druckachse relevant.
# run1/run2 = Lauf E/F (gestrippte GVs ohne GvpC); laufB/laufD = die frueheren
# Laeufe mit intakten purified GVs.
PRESETS = {
    "laufB": dict(
        phot=DATA / "photometer" / "photometer-20260907-015718.csv",
        itv=DATA / "itv-20260907-015859.csv",
        skip=0,       # kein Startup-Peak -- A500 von Punkt 1 an flach bei ~0,475
        offset=0.0,   # Handstart, Versatz nicht exakt bekannt; A500 flach -> egal
        label="Lauf B -- purified GVs (intakt) im Setup, randvoll gefuellte Kuevette",
        syringe="0.494,0.492,0.496;0.310,0.309,0.308",
        syringe_labels="vorher;~10 min danach (= Lauf C)",
        refs={},      # die -37 %-Referenz IST hier die eigene Spritze (Lauf C)
    ),
    "laufD": dict(
        phot=DATA / "photometer" / "photometer-20260907-034819.csv",
        itv=DATA / "itv-20260907-034837.csv",
        skip=6,       # P1-6 Startup-Blasen (Teilfuellung), dokumentiert
        offset=18.0,  # ITV-Log ~18 s nach der Kinetik gestartet, dokumentiert
        label="Lauf D -- purified GVs (intakt) im Setup, teilgefuellte Kuevette",
        syringe="0.597,0.600,0.599;0.265,0.263,0.262;0.272,0.270,0.267",
        syringe_labels="vorher;direkt danach;~10 min danach",
        refs={},      # die -55 %-Referenz IST hier die eigene Spritze
    ),
    "run1": dict(
        phot=DATA / "photometer" / "photometer-20260907-191024.csv",
        itv=DATA / "itv-20260907-191033.csv",
        skip=10,
        offset=9.0,
        label="Lauf 1 -- gestrippte GVs in reinem Stripping-Buffer",
        syringe="0.270,0.269,0.265;0.273,0.258,0.251;0.226,0.230,0.232",
        syringe_labels="vorher;direkt danach;~13 min danach",
    ),
    "run2": dict(
        phot=DATA / "photometer" / "photometer-20260907-192920.csv",
        itv=DATA / "itv-20260907-193413.csv",
        skip=6,
        offset=9.0,   # Logger-Startzeitstempel 293 s auseinander = Logger frueh
                      # gestartet, NICHT der Lauf; echter Versatz unbekannt.
        label="Lauf 2 -- gestrippte GVs in ~50 % PBS / 50 % Stripping-Buffer",
        syringe="0.387,0.385,0.387;0.387,0.375,0.370;0.362,0.360,0.360",
        syringe_labels="vorher;direkt danach;~10 min danach",
    ),
    "laufG": dict(
        phot=DATA / "photometer" / "photometer-20260908-145728.csv",
        itv=DATA / "itv-20260908-150354.csv",
        skip=5,       # P1-5 Startup-Peak (P2-3 railen bei 2.5), ab P6 flach ~0.48
        offset=0.0,   # Logger praktisch gleichzeitig gestartet: ITV-Sweep-Ende
                      # (t_s 416 s) faellt mit dem Entlastungs-Sprung im Photometer
                      # (Punkt 52, ~416 s) zusammen -> Versatz ~0.
        label="Lauf G -- purified Serratia-GVs MIT GvpC (intakt), Bestaetigungslauf 2026-09-08",
        syringe="0.546,0.546,0.546;0.468,0.471,0.470;0.452,0.450,0.450",
        syringe_labels="vorher;direkt danach;10 min danach",
    ),
}


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
    out, prev = [], -1
    for r in rows:
        sec = parse_hms(r["time"])
        if sec is None or sec <= prev:
            break
        out.append(r)
        prev = sec
    return out if len(out) >= 3 else rows


def load_photometer(path, interval):
    rows = leading_kinetics(list(csv.DictReader(open(path))))
    a = np.array([float(r["value"]) for r in rows])
    t = np.arange(len(rows)) * interval
    return t, a


def load_itv(path, offset):
    rows = list(csv.DictReader(open(path)))
    t = np.array([float(r["t_s"]) - offset for r in rows])
    bar = np.array([ist_bar(float(r["monitor_v"])) for r in rows])
    return t, bar


def mean_pressure_per_interval(t_phot, interval, t_itv, bar_itv):
    """Pro Photometer-Fenster [t0, t0+interval) gemittelter Ist-Druck.
    Fenster komplett hinter dem ITV-Log-Ende -> 0 bar (Sweep vorbei, drucklos)."""
    itv_end = t_itv.max()
    press, covered = [], []
    for t0 in t_phot:
        m = (t_itv >= t0) & (t_itv < t0 + interval)
        if m.any():
            press.append(float(bar_itv[m].mean()))
            covered.append(True)
        elif t0 >= itv_end:
            press.append(0.0)
            covered.append(False)
        else:
            press.append(np.nan)
            covered.append(False)
    return np.array(press), np.array(covered, dtype=bool)


def parse_syringe(spec, label_spec):
    if not spec:
        return None
    reps = [[float(x) for x in grp.split(",") if x.strip()]
            for grp in spec.split(";") if grp.strip()]
    labels = ([s.strip() for s in label_spec.split(";")] if label_spec
              else [f"t{i}" for i in range(len(reps))])
    if len(labels) != len(reps):
        labels = [f"t{i}" for i in range(len(reps))]
    means = [float(np.mean(r)) for r in reps]
    sds = [float(np.std(r, ddof=1)) if len(r) > 1 else 0.0 for r in reps]
    return dict(reps=reps, labels=labels, means=means, sds=sds)


def _interp_crossing(xs, ys, y_target):
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if (y0 - y_target) * (y1 - y_target) <= 0 and y0 != y1:
            f = (y_target - y0) / (y1 - y0)
            return x0 + f * (x1 - x0)
    return None


def boltzmann(P, a_high, a_low, p50, dp):
    """Fallende 4-Parameter-Boltzmann-Sigmoide (dp > 0 -> fallend).
    Identisch zu fit_collapse_pressure.py."""
    return a_low + (a_high - a_low) / (1.0 + np.exp((P - p50) / dp))


def fit_collapse(press, a):
    """press, a: 1D-Arrays des ITV-gedeckten Hochramp-Asts. -> dict mit
    Parametern, 1-sigma-Fehlern, abgeleiteten Druecken und R^2.
    Wortgleich zu fit_collapse_pressure.fit_collapse()."""
    order = np.argsort(press)
    P = np.asarray(press, float)[order]
    A = np.asarray(a, float)[order]

    a_high0 = float(np.mean(A[:max(3, len(A) // 5)]))
    a_low0 = float(np.mean(A[-max(3, len(A) // 5):]))
    p50_0 = float(np.interp(0.5 * (a_high0 + a_low0), A[::-1], P[::-1])) \
        if a_high0 != a_low0 else float(np.median(P))
    p0 = [a_high0, a_low0, p50_0, 1.0]
    span = max(A.max() - A.min(), 1e-3)
    bounds = (
        [A.min() - span, A.min() - span, P.min() - 1.0, 0.05],
        [A.max() + span, A.max() + span, P.max() + 1.0, max(P.max() - P.min(), 2.0)],
    )
    popt, pcov = curve_fit(boltzmann, P, A, p0=p0, bounds=bounds, maxfev=20000)
    perr = np.sqrt(np.diag(pcov))
    a_high, a_low, p50, dp = popt

    resid = A - boltzmann(P, *popt)
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((A - A.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    amp = a_high - a_low
    return dict(
        a_high=a_high, a_low=a_low, p50=p50, dp=dp,
        a_high_err=perr[0], a_low_err=perr[1], p50_err=perr[2], dp_err=perr[3],
        amplitude=amp, slope_at_p50=-amp / (4.0 * dp),
        p_onset=p50 - _K_5_95 * dp, p_95=p50 + _K_5_95 * dp,
        width_10_90=_K_10_90 * dp, r2=r2, n=len(P),
        drop_pct=amp / a_high * 100.0 if a_high else float("nan"),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, nargs="?", default=None,
                    help="photometer_capture.py-CSV (time,label,value) -- entfaellt bei --preset")
    ap.add_argument("--preset", choices=sorted(PRESETS), default=None,
                    help="bekannten Lauf laden (Dateien/skip/offset/Spritze vorbelegen)")
    ap.add_argument("--itv", type=Path, default=None,
                    help="gepaarte capture.py-Druck-CSV (t_s,dir,soll_v,loopback_v,monitor_v)")
    ap.add_argument("--skip", type=int, default=None, metavar="N",
                    help="erste N Kinetik-Punkte: raus aus dem clean Graph (b) UND aus "
                         "Baseline/Kollapskurve/Kennzahlen (Panel a zeigt trotzdem alles)")
    ap.add_argument("--offset", type=float, default=None,
                    help="Zeitversatz des ITV-Logs in s (positiv = ITV spaeter gestartet)")
    ap.add_argument("--interval", type=float, default=INTERVAL_S, metavar="SEC",
                    help=f"Kinetik-Punktintervall (Default {INTERVAL_S} s, Live-Sync-Wert)")
    ap.add_argument("--syringe", default=None,
                    help='Spritzen-Triplikate, Zeitpunkte per ";", Reps per ",": '
                         '"0.27,0.27,0.27;0.27,0.26,0.25;0.23,0.23,0.23"')
    ap.add_argument("--syringe-labels", default=None,
                    help='Labels zu --syringe, per ";": "vorher;direkt danach;spaet"')
    ap.add_argument("--label", default=None, help="Lauf-Bezeichnung (Titel)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    # Preset ausrollen, explizite Flags haben Vorrang
    p = PRESETS.get(args.preset, {})
    phot = args.csv or p.get("phot")
    itv = args.itv or p.get("itv")
    skip = args.skip if args.skip is not None else p.get("skip", 0)
    offset = args.offset if args.offset is not None else p.get("offset", 0.0)
    label = args.label or p.get("label") or (Path(phot).name if phot else "Lauf")
    syr_spec = args.syringe if args.syringe is not None else p.get("syringe")
    syr_lab = args.syringe_labels if args.syringe_labels is not None else p.get("syringe_labels")
    refs = p.get("refs", REF_SYRINGE_PCT)

    if not phot or not itv:
        ap.error("Photometer-CSV und --itv noetig (oder --preset run1|run2|laufB|laufD).")

    interval = args.interval
    t_phot, a = load_photometer(phot, interval)
    t_itv, bar_itv = load_itv(itv, offset)
    syr = parse_syringe(syr_spec, syr_lab)

    n = len(a)
    skip = max(0, min(skip, n - 6))
    tk, ak = t_phot[skip:], a[skip:]
    press, covered = mean_pressure_per_interval(tk, interval, t_itv, bar_itv)

    baseline = float(np.mean(ak[:5]))
    plateau = float(np.mean(ak[-5:]))
    a_min = float(np.min(ak))
    i_min = int(np.argmin(ak))
    p_at_min = float(press[i_min]) if np.isfinite(press[i_min]) else float("nan")
    setup_net_pct = (plateau - baseline) / baseline * 100.0

    # Kollaps-Kennlinie nur ueber den Teil unter Druck (monoton steigend) --
    # und nur, wenn es ueberhaupt einen echten Abfall gibt (Endplateau >5 %
    # unter Baseline). Sonst waeren Onset/P50 blosses Rauschen.
    has_drop = setup_net_pct <= -5.0
    up = sorted((float(pp), float(y)) for pp, y in zip(press, ak)
                if np.isfinite(pp) and pp > 0.05)
    xs, ys = [u[0] for u in up], [u[1] for u in up]
    p_onset = (_interp_crossing(xs, ys, baseline * 0.95)
               if has_drop and len(xs) > 2 else None)
    p50 = (_interp_crossing(xs, ys, (baseline + plateau) / 2.0)
           if has_drop and len(xs) > 2 else None)

    # --- Boltzmann-Fit ueber den ITV-gedeckten Hochramp-Ast (wie
    #     fit_collapse_pressure.py). Nur wenn es ueberhaupt einen echten
    #     Abfall gibt -- sonst waere der Wendepunkt blosses Rauschen.
    ramp = covered & np.isfinite(press) & (press > 0.05)
    fit = None
    if has_drop and int(ramp.sum()) >= 5:
        try:
            fit = fit_collapse(press[ramp], ak[ramp])
        except Exception as exc:  # RuntimeError (kein Optimum), ValueError ...
            print(f"  ! Boltzmann-Fit fehlgeschlagen ({exc}) -- Panel (c) zeigt "
                  f"nur die lineare P50-Schaetzung.")

    # --- Konsole --------------------------------------------------------
    print(f"\n=== {label} ===")
    print(f"  Phot : {Path(phot).name}   (skip {skip} von {n})")
    print(f"  ITV  : {Path(itv).name}    (offset {offset:.0f} s, interval {interval} s)")
    print(f"  Baseline A500 (erste 5 nach skip): {baseline:.3f}")
    print(f"  Endplateau A500 (letzte 5):        {plateau:.3f}"
          f"   -> netto {setup_net_pct:+.1f} %  ({'OD STEIGT' if setup_net_pct >= 0 else 'OD faellt'}, "
          f"{'kein Kollaps' if setup_net_pct > -5 else 'moeglicher Kollaps'})")
    print(f"  Minimum A500:                      {a_min:.3f}  bei ~{p_at_min:.1f} bar"
          f"  ({(a_min-baseline)/baseline*100:+.1f} % ggue. Baseline, transient)")
    if p_onset:
        print(f"  Kollaps-Onset (A < 95 % Baseline): ~{p_onset:.2f} bar  (linear interpoliert)")
    if p50:
        print(f"  Halbkollaps-Druck P50:            ~{p50:.2f} bar  (linear interpoliert)")
    if fit is not None:
        print(f"  Boltzmann-Fit ({fit['n']} Ramp-Punkte):  "
              f"A {fit['a_high']:.3f} -> {fit['a_low']:.3f} A500 ({fit['drop_pct']:.0f} %), "
              f"dP {fit['dp']:.2f} bar, R^2 {fit['r2']:.3f}")
        print(f"  >>> KOLLAPSDRUCK P50 = {fit['p50']:.2f} +/- {fit['p50_err']:.2f} bar "
              f"(Sigmoid-Wendepunkt) | Onset P05 ~{fit['p_onset']:.2f} | P95 ~{fit['p_95']:.2f} <<<")
    if syr:
        for lab, m, s in zip(syr["labels"], syr["means"], syr["sds"]):
            print(f"  Spritze {lab:>18}: {m:.3f} +/- {s:.3f}")
        s_net = (syr["means"][-1] - syr["means"][0]) / syr["means"][0] * 100.0
        print(f"  Spritze netto (vorher -> spaet):   {s_net:+.1f} %")
    else:
        s_net = None

    # --- Figur ---------------------------------------------------------
    A_COL, P_COL = "#1f77b4", "#555555"
    fig = plt.figure(figsize=(13, 15.5), dpi=150)
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1, 0.9],
                          hspace=0.42, wspace=0.26, top=0.94, bottom=0.045)

    def timeseries(ax, i0, sub):
        c = A_COL
        ax.plot(t_phot[i0:] / 60, a[i0:], "o-", ms=3.2, lw=1.3, color=c,
                label="A500 (Biowave II)")
        ax.set_xlabel("Zeit seit Kinetik-Start (min)")
        ax.set_ylabel("Absorption A500", color=c)
        ax.tick_params(axis="y", labelcolor=c)
        ax.grid(True, alpha=0.3)
        ax2 = ax.twinx()
        ax2.plot(t_itv / 60, bar_itv, lw=1.0, color=P_COL, alpha=0.85,
                 label="Ist-Druck (ITV-Monitor)")
        ax2.set_ylabel("Ist-Druck (bar)", color=P_COL)
        ax2.tick_params(axis="y", labelcolor=P_COL)
        ax2.set_ylim(bottom=0)
        lines = ax.get_lines()[:1] + ax2.get_lines()
        ax.legend(lines, [ln.get_label() for ln in lines], loc="upper left", fontsize=8)
        ax.set_title(sub, fontsize=9.5)
        return ax2

    # (a) alle Messwerte
    axa = fig.add_subplot(gs[0, :])
    timeseries(axa, 0, "(a) Zeit vs. A500 / Ist-Druck -- ALLE Messwerte (Rohdaten, inkl. Startup-Peak)")
    if skip:
        axa.axvspan(0, skip * interval / 60, color="0.85", alpha=0.6, zorder=0)
        axa.text(skip * interval / 60, axa.get_ylim()[1], f" erste {skip} Punkte",
                 fontsize=7.5, va="top", color="#666")

    # (b) erste skip ausgeblendet
    axb = fig.add_subplot(gs[1, :])
    timeseries(axb, skip, f"(b) Zeit vs. A500 / Ist-Druck -- erste {skip} Punkte ausgeblendet (clean, fuer die Auswertung)")

    # (c) A500 vs. Ist-Druck
    axc = fig.add_subplot(gs[2, 0])
    m = np.isfinite(press) & covered
    order = np.argsort(press[m])
    axc.plot(press[m][order], ak[m][order], "o-", ms=4, lw=1.0, color=A_COL)
    pm = (~covered) & np.isfinite(press)
    if pm.any():
        axc.scatter(press[pm], ak[pm], s=28, facecolor="none", edgecolor=A_COL,
                    linewidth=1.2, label="nach Sweep-Ende, drucklos")
    axc.axhline(baseline, ls="-", lw=1, color="#888", alpha=0.8)
    axc.axhline(plateau, ls=":", lw=1, color="#888", alpha=0.8)
    axc.axvspan(*COLLAPSE_BAND_BAR, color="#2ca02c", alpha=0.12, label="erwartetes Kollapsband")
    if p50:
        axc.axvline(p50, ls="--", lw=1, color="#d62728", alpha=0.7, label=f"P50 ~{p50:.1f} bar")
    axc.set_xlabel("Ist-Druck, pro Kinetik-Intervall gemittelt (bar)")
    axc.set_ylabel("Absorption A500")
    axc.grid(True, alpha=0.3)
    axc.legend(fontsize=7.5)
    axc.set_title("(c) A500 vs. Druck -- durchgezogen = Baseline, gepunktet = Endplateau", fontsize=9)
    axr = axc.twinx()
    lo, hi = axc.get_ylim()
    axr.set_ylim(lo / baseline, hi / baseline)
    axr.set_ylabel("A500 / A500(Baseline)", color="#999")
    axr.tick_params(axis="y", labelcolor="#999")

    # (d) Spritzen-Test
    axd = fig.add_subplot(gs[2, 1])
    if syr:
        x = np.arange(len(syr["means"]))
        axd.bar(x, syr["means"], 0.55, yerr=syr["sds"], capsize=4, color="#2ca02c", alpha=0.85)
        for xi, mm, ss in zip(x, syr["means"], syr["sds"]):
            axd.text(xi, mm + ss + 0.004, f"{mm:.3f}", ha="center", fontsize=8)
        axd.set_xticks(x)
        axd.set_xticklabels([l.replace(" ", "\n", 1) for l in syr["labels"]], fontsize=8)
        axd.set_ylabel("OD (Biowave II, 500 nm)")
        axd.set_ylim(0, max(syr["means"]) * 1.25)
        axd.grid(True, axis="y", alpha=0.3)
    else:
        axd.text(0.5, 0.5, "keine Spritzendaten (--syringe)", ha="center", va="center",
                 transform=axd.transAxes, color="#888")
    axd.set_title("(d) Spritzen-Kontrolle (~4-5 bar) -- Mittel +/- SD, Triplikat", fontsize=9)

    # (e) Netto-% Setup vs. Spritze
    axe = fig.add_subplot(gs[3, 0])
    bars, vals, cols = ["Setup\nBaseline->Plateau"], [setup_net_pct], ["#8c8c8c"]
    if s_net is not None:
        bars.append("Spritze\nvorher->spaet"); vals.append(s_net); cols.append("#2ca02c")
    xx = np.arange(len(bars))
    axe.bar(xx, vals, 0.5, color=cols)
    for xi, v in zip(xx, vals):
        axe.text(xi, v + (1.5 if v >= 0 else -1.5), f"{v:+.0f}%", ha="center",
                 fontsize=9, va="bottom" if v >= 0 else "top")
    for name, refv in refs.items():
        axe.axhline(refv, ls=":", color="#bbb", lw=1)
        axe.text(len(bars) - 0.5, refv, f" {name} Spritze {refv:+.0f}%", fontsize=7,
                 va="bottom", ha="right", color="#888")
    axe.axhline(0, color="k", lw=0.8)
    axe.set_xticks(xx); axe.set_xticklabels(bars, fontsize=8)
    axe.set_ylabel("Netto-Aenderung OD (%)")
    axe.set_ylim(min(-62, min(vals) - 8), max(15, max(vals) + 10))
    axe.grid(True, axis="y", alpha=0.3)
    axe.set_title("(e) Kollaps-Ausbeute: Setup vs. Spritze", fontsize=9)

    # (f) Kennzahlen
    axf = fig.add_subplot(gs[3, 1])
    axf.axis("off")
    lines = [
        f"Datei Phot : {Path(phot).name}",
        f"Datei ITV  : {Path(itv).name}",
        f"skip / interval / offset : {skip}  /  {interval} s  /  {offset:.0f} s",
        "",
        f"Baseline A500 (5 n. skip) : {baseline:.3f}",
        f"Endplateau A500 (letzte 5): {plateau:.3f}   ({setup_net_pct:+.1f} %)",
        f"Minimum A500              : {a_min:.3f}  @ ~{p_at_min:.1f} bar"
        f"  ({(a_min-baseline)/baseline*100:+.1f} %)",
        f"Kollaps-Onset            : {('~%.1f bar' % p_onset) if p_onset else '--'}",
        f"P50                      : {('~%.1f bar' % p50) if p50 else '--'}",
    ]
    if syr:
        lines += [
            "",
            f"Spritze vorher -> spaet   : {syr['means'][0]:.3f} -> {syr['means'][-1]:.3f}"
            f"   ({s_net:+.1f} %)",
        ]
    axf.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", family="monospace",
             fontsize=8.5, transform=axf.transAxes)
    axf.set_title("(f) Kennzahlen", fontsize=9, loc="left")

    fig.suptitle(f"{label}\nHydrostatik-Setup, 2026-09-07  --  Blank = purer Stripping-Buffer",
                 fontsize=11, y=0.985)

    out = args.out or (VAULT_ROOT / "assets" / "Hydrostatic-Pressure-Setup" / "sweeps"
                       / f"stripped-gv_summary_{Path(phot).stem}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    print(f"\ngespeichert: {out}")


if __name__ == "__main__":
    main()
