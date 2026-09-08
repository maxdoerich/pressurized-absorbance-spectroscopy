#!/usr/bin/env python3
"""Sigmoid-/Boltzmann-Fit der Kollaps-Kennlinie -> Kollapsdruck (P50) + Diagramm.

Nimmt einen Hydrostatik-Sync-Lauf (Photometer-Kinetics-Mitschnitt + gepaarter
ITV-Sweep), traegt A500 gegen den *pro Kinetik-Intervall gemittelten* Ist-Druck
auf (wie plot_od_vs_pressure.py) und fittet an den Hochramp-Teil eine fallende
4-Parameter-Boltzmann-Funktion:

    A(P) = A_low + (A_high - A_low) / (1 + exp((P - P50) / dP))          dP > 0

Der Wendepunkt P50 ist der **Kollapsdruck** (halbe GV-Population kollabiert).
Zusaetzlich ausgegeben:
  * dP           -- Breite der Uebergangszone (bar); Steigung im Wendepunkt
                    = -(A_high - A_low) / (4 dP)
  * Onset  P05   -- 5 % Abfall erreicht  = P50 - 2.944 dP
  * P95         -- 95 % kollabiert       = P50 + 2.944 dP
  * 10-90-%-Breite = 4.394 dP
  * R^2 des Fits, 1-sigma-Fehler aller Parameter (aus der Kovarianzmatrix)

WICHTIG:
  * Gefittet wird NUR der Ast unter steigendem Druck (P > 0.05 bar, ITV-gedeckt).
    Die drucklos nach dem Sweep gemessenen Punkte (irreversibler Kollaps) liegen
    NICHT auf der Gleichgewichts-Sigmoide und werden nur zur Kontrolle als offene
    Kreise geplottet, nicht gefittet.
  * Biowave-"5 s"-Kinetik sampelt real ~8.16 s (Live-Sync-Test 2026-08-24) -->
    Default-Intervall 8.16 s; nur bei abweichender Sweep-Haltezeit --interval setzen.
  * Kalibrierkonstanten (P_FULL_BAR / MONITOR_V_*) identisch zu capture.py /
    plot_sweep.py / plot_photometer.py / plot_od_vs_pressure.py.

Usage:
    # bekannter Lauf ueber Preset (Dateien/skip/offset vorbelegt):
    python3 fit_collapse_pressure.py --preset laufD

    # beliebiger Lauf, alles explizit:
    python3 fit_collapse_pressure.py data/photometer/photometer-<stamp>.csv \
        --itv data/itv-<stamp>.csv --skip 6 --offset 18 \
        --title "..." --out /pfad/out.png

Default-Output:
    PNG : assets/Hydrostatic-Pressure-Setup/sweeps/kollapsfit_<phot-stem>.png
    CSV : daneben, kollapsfit_<phot-stem>.csv  (Fit-Parameter + abgeleitete Druecke)
"""
import argparse
import csv
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ITV0050-Kalibrierung -- identisch zu den anderen Programme/-Skripten.
P_FULL_BAR = 9.0
MONITOR_V_ZERO = 1.0
MONITOR_V_MAX = 5.0

# Biowave-"5 s"-Kinetik sampelt real ~8.16 s (Live-Sync-Test 2026-08-24).
INTERVAL_S = 8.16

# erwartetes Serratia-GV-Kollapsband (Bacterial-GV-Expression-Overview: ~3.5-5.4 bar)
COLLAPSE_BAND_BAR = (3.5, 5.4)

# ln(0.95/0.05) -- Druckabstand vom Wendepunkt zu 5 %- bzw. 95 %-Kollaps, in dP.
_K_5_95 = float(np.log(0.95 / 0.05))          # ~= 2.9444
# 10-90-%-Breite in Einheiten von dP: 2 * ln(9)
_K_10_90 = float(2.0 * np.log(9.0))           # ~= 4.3944

VAULT_ROOT = Path(__file__).resolve().parents[3]
DATA = Path(__file__).resolve().parent / "data"

PRESETS = {
    # Lauf D -- erster nachgewiesener GV-Kollaps IM Setup (2026-09-07 nachts),
    # intaktes 2. GV-Sample, teilgefuellte Kuevette. skip/offset dokumentiert.
    "laufD": dict(
        phot=DATA / "photometer" / "photometer-20260907-034819.csv",
        itv=DATA / "itv-20260907-034837.csv",
        skip=6,
        offset=18.0,
        title="Lauf D -- purified Serratia-GVs, Kollaps-Fit (A500 vs. Ist-Druck)",
    ),
    # Lauf B -- volle Kuevette, andere Charge, KEIN Kollaps. Nur zum Vergleich;
    # der Fit wird hier bewusst scheitern/flach sein (Warnung wird ausgegeben).
    "laufB": dict(
        phot=DATA / "photometer" / "photometer-20260907-015718.csv",
        itv=DATA / "itv-20260907-015859.csv",
        skip=0,
        offset=0.0,
        title="Lauf B -- purified GVs, volle Kuevette (Kontrolle, kein Kollaps erwartet)",
    ),
}


# --------------------------------------------------------------------------- #
# Laden / Aufbereiten  (Konventionen aus plot_od_vs_pressure.py)             #
# --------------------------------------------------------------------------- #
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
    """Erste Kinetics-Serie (streng steigende Zeitstempel) -- Rest abschneiden."""
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
    a = np.array([float(r["value"]) for r in rows])
    t = np.arange(len(rows)) * interval
    return t[skip:], a[skip:]


def load_itv(path, offset):
    rows = list(csv.DictReader(open(path)))
    if not rows:
        raise SystemExit(f"Keine Daten in {path}")
    t = np.array([float(r["t_s"]) - offset for r in rows])
    bar = np.array([ist_bar(float(r["monitor_v"])) for r in rows])
    return t, bar


def mean_pressure_per_interval(t_phot, interval, t_itv, bar_itv):
    """-> (press, covered) je Photometer-Fenster [t0, t0+interval).

    covered=False + press=0.0  -> Fenster liegt hinter dem ITV-Log-Ende (Sweep
    vorbei, Druck abgelassen).  covered=False + press=nan -> gar keine Deckung.
    """
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


# --------------------------------------------------------------------------- #
# Fit                                                                        #
# --------------------------------------------------------------------------- #
def boltzmann(P, a_high, a_low, p50, dp):
    """Fallende 4-Parameter-Boltzmann-Sigmoide (dp > 0 -> fallend)."""
    return a_low + (a_high - a_low) / (1.0 + np.exp((P - p50) / dp))


def _interp_crossing(xs, ys, y_target):
    """Erste lineare Kreuzung von y_target -- modellfreie Onset-/P50-Kontrolle."""
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if (y0 - y_target) * (y1 - y_target) <= 0 and y0 != y1:
            f = (y_target - y0) / (y1 - y0)
            return x0 + f * (x1 - x0)
    return None


def fit_collapse(press, a):
    """press, a: 1D-Arrays des Hochramp-Asts (aufsteigend nach Druck sortiert).
    -> dict mit Parametern, Fehlern, abgeleiteten Druecken und R^2.
    """
    order = np.argsort(press)
    P = np.asarray(press, float)[order]
    A = np.asarray(a, float)[order]

    a_high0 = float(np.mean(A[:max(3, len(A) // 5)]))         # Plateau bei niedrigem P
    a_low0 = float(np.mean(A[-max(3, len(A) // 5):]))         # Plateau bei hohem P
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
        amplitude=amp,
        slope_at_p50=-amp / (4.0 * dp),
        p_onset=p50 - _K_5_95 * dp,          # 5 % Abfall
        p_95=p50 + _K_5_95 * dp,             # 95 % kollabiert
        width_10_90=_K_10_90 * dp,
        r2=r2, n=len(P),
        drop_pct=amp / a_high * 100.0 if a_high else float("nan"),
    )


# --------------------------------------------------------------------------- #
# main                                                                       #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, nargs="?", default=None,
                    help="photometer_capture.py-CSV (time,label,value) -- entfaellt bei --preset")
    ap.add_argument("--preset", choices=sorted(PRESETS), default=None,
                    help="bekannten Lauf laden (Dateien/skip/offset vorbelegen)")
    ap.add_argument("--itv", type=Path, default=None,
                    help="gepaarte capture.py-Druck-CSV (t_s,dir,soll_v,loopback_v,monitor_v)")
    ap.add_argument("--interval", type=float, default=INTERVAL_S, metavar="SEC",
                    help=f"Kinetik-Punktintervall (Default {INTERVAL_S} s, Live-Sync-Wert)")
    ap.add_argument("--offset", type=float, default=None,
                    help="Zeitversatz des ITV-Logs in s (positiv = ITV spaeter gestartet)")
    ap.add_argument("--skip", type=int, default=None, metavar="N",
                    help="erste N Photometer-Punkte weglassen (Startup-/Blasen-Artefakte)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output-PNG (Default: assets/Hydrostatic-Pressure-Setup/sweeps/kollapsfit_<stem>.png)")
    ap.add_argument("--title", default=None, help="eigener Plot-Titel")
    ap.add_argument("--ylim", type=float, nargs=2, default=None, metavar=("LO", "HI"),
                    help="feste A-Achse, sonst Autoskala")
    args = ap.parse_args()

    p = PRESETS.get(args.preset, {})
    phot = args.csv or p.get("phot")
    itv = args.itv or p.get("itv")
    skip = args.skip if args.skip is not None else p.get("skip", 0)
    offset = args.offset if args.offset is not None else p.get("offset", 0.0)
    title = args.title or p.get("title")
    if not phot or not itv:
        ap.error("Photometer-CSV und --itv noetig (oder --preset laufD).")
    phot, itv = Path(phot), Path(itv)

    out = args.out or (VAULT_ROOT / "assets" / "Hydrostatic-Pressure-Setup"
                       / "sweeps" / f"kollapsfit_{phot.stem}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    csv_out = out.with_suffix(".csv")

    # --- CSV frueh anlegen, Zeilen fortschreiben (Vault-Konvention) ----------
    cf = open(csv_out, "w", newline="")
    cw = csv.writer(cf)
    cw.writerow(["groesse", "wert", "einheit", "bemerkung"])
    cw.writerow(["photometer_csv", phot.name, "", ""])
    cw.writerow(["itv_csv", itv.name, "", ""])
    cw.writerow(["skip", skip, "Punkte", "erste N Kinetik-Punkte verworfen"])
    cw.writerow(["offset", f"{offset:.1f}", "s", "ITV-Log-Zeitversatz"])
    cw.writerow(["interval", f"{args.interval:.2f}", "s", "Kinetik-Punktintervall"])
    cf.flush()

    # --- Daten -------------------------------------------------------------
    t_phot, a = load_photometer(phot, args.interval, skip)
    t_itv, bar_itv = load_itv(itv, offset)
    press, covered = mean_pressure_per_interval(t_phot, args.interval, t_itv, bar_itv)

    ramp = covered & np.isfinite(press) & (press > 0.05)
    depress = (~covered) & np.isfinite(press)          # drucklos nach Sweep-Ende
    if ramp.sum() < 5:
        cf.close()
        raise SystemExit(f"Zu wenige Punkte unter Druck fuer einen Fit ({ramp.sum()}).")
    P_fit, A_fit = press[ramp], a[ramp]

    # modellfreie Kennzahlen (zur Kontrolle / Warnung)
    base_lin = float(np.mean(A_fit[np.argsort(P_fit)][:5]))
    plat_lin = float(np.mean(A_fit[np.argsort(P_fit)][-5:]))
    net_pct = (plat_lin - base_lin) / base_lin * 100.0

    fit = fit_collapse(P_fit, A_fit)

    # --- Fit-Ergebnisse in CSV ------------------------------------------
    for k, unit, note in [
        ("p50", "bar", "Kollapsdruck (Wendepunkt der Sigmoide)"),
        ("p50_err", "bar", "1-sigma"),
        ("dp", "bar", "Breite der Uebergangszone"),
        ("dp_err", "bar", "1-sigma"),
        ("p_onset", "bar", "5 %-Kollaps (P50 - 2.944 dP)"),
        ("p_95", "bar", "95 %-Kollaps (P50 + 2.944 dP)"),
        ("width_10_90", "bar", "10-90 %-Breite (4.394 dP)"),
        ("a_high", "A500", "Plateau bei niedrigem Druck (Baseline)"),
        ("a_high_err", "A500", "1-sigma"),
        ("a_low", "A500", "Plateau bei hohem Druck (kollabiert)"),
        ("a_low_err", "A500", "1-sigma"),
        ("amplitude", "A500", "a_high - a_low"),
        ("drop_pct", "%", "Fit-Amplitude relativ zur Baseline"),
        ("slope_at_p50", "A500/bar", "Steigung im Wendepunkt"),
        ("r2", "", "Bestimmtheitsmass des Fits"),
        ("n", "Punkte", "in den Fit eingegangene Ramp-Punkte"),
    ]:
        v = fit[k]
        cw.writerow([k, f"{v:.4f}" if isinstance(v, float) else v, unit, note])
    cw.writerow(["net_pct_linear", f"{net_pct:.1f}", "%",
                 "modellfrei: (Plateau-Baseline)/Baseline ueber den Ramp-Ast"])
    cf.flush()
    cf.close()

    # --- Konsole ---------------------------------------------------------
    print(f"\n=== Kollaps-Fit  --  {phot.name} ===")
    print(f"  ITV {itv.name}   skip {skip}   offset {offset:.0f} s   interval {args.interval} s")
    print(f"  Ramp-Punkte im Fit: {fit['n']}   |   drucklose Kontrollpunkte: {int(depress.sum())}")
    print(f"  modellfrei: Baseline {base_lin:.3f} -> Plateau {plat_lin:.3f}  ({net_pct:+.1f} %)")
    if net_pct > -10:
        print("  ! WARNUNG: kaum/kein OD-Abfall auf dem Ramp-Ast -- P50 ist hier "
              "nicht aussagekraeftig (Kontroll-Lauf?).")
    print(f"\n  Boltzmann-Fit  A(P) = a_low + (a_high-a_low)/(1+exp((P-P50)/dP))")
    print(f"    a_high (Baseline)   = {fit['a_high']:.3f} +/- {fit['a_high_err']:.3f}  A500")
    print(f"    a_low  (kollabiert) = {fit['a_low']:.3f} +/- {fit['a_low_err']:.3f}  A500")
    print(f"    Amplitude           = {fit['amplitude']:.3f}  A500  ({fit['drop_pct']:.0f} % der Baseline)")
    print(f"    dP (Uebergang)      = {fit['dp']:.2f} +/- {fit['dp_err']:.2f}  bar")
    print(f"    R^2                 = {fit['r2']:.4f}")
    print(f"\n  >>> KOLLAPSDRUCK  P50 = {fit['p50']:.2f} +/- {fit['p50_err']:.2f} bar <<<")
    print(f"      Onset (5 %)   P05 ~ {fit['p_onset']:.2f} bar")
    print(f"      95 %-Kollaps  P95 ~ {fit['p_95']:.2f} bar")
    print(f"      10-90-%-Breite    ~ {fit['width_10_90']:.2f} bar")
    print(f"      Steigung @P50      = {fit['slope_at_p50']:.3f} A500/bar")

    # --- Plot ----------------------------------------------------------
    A_COL = "#1f77b4"
    fig, ax = plt.subplots(figsize=(9.5, 6.2), dpi=150)

    t_ramp_min = t_phot[ramp] / 60.0
    sc = ax.scatter(P_fit, A_fit, c=t_ramp_min, cmap="viridis", s=40, zorder=3,
                    edgecolor="white", linewidth=0.4, label="Messpunkte (Hochrampe)")
    if depress.any():
        ax.scatter(np.zeros(depress.sum()), a[depress], s=34, facecolor="none",
                   edgecolor="#888888", linewidth=1.1, zorder=2,
                   label="drucklos nach Sweep (nicht gefittet)")

    # Fit-Kurve
    P_grid = np.linspace(0.0, max(P_fit.max() * 1.03, fit["p_95"] + 1.0), 400)
    ax.plot(P_grid, boltzmann(P_grid, fit["a_high"], fit["a_low"], fit["p50"], fit["dp"]),
            "-", color="#d62728", lw=2.0, zorder=4,
            label="Boltzmann-Fit")

    ax.axhline(fit["a_high"], ls="-", lw=0.9, color="#999999", alpha=0.8)
    ax.axhline(fit["a_low"], ls=":", lw=0.9, color="#999999", alpha=0.8)
    ax.axvspan(fit["p_onset"], fit["p_95"], color="#d62728", alpha=0.08,
               label=f"Uebergang P05-P95 ({fit['p_onset']:.1f}-{fit['p_95']:.1f} bar)")
    ax.axvspan(*COLLAPSE_BAND_BAR, color="#2ca02c", alpha=0.10,
               label=f"erwartetes Serratia-Band {COLLAPSE_BAND_BAR[0]}-{COLLAPSE_BAND_BAR[1]} bar")
    ax.axvline(fit["p50"], ls="--", lw=1.6, color="#d62728", zorder=4)
    ax.annotate(f"Kollapsdruck  P50 = {fit['p50']:.2f} $\\pm$ {fit['p50_err']:.2f} bar",
                xy=(fit["p50"], fit["a_high"]),
                xytext=(0.97, 0.93), textcoords="axes fraction",
                ha="right", va="top", fontsize=11, fontweight="bold", color="#d62728",
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#d62728", alpha=0.9))

    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("Zeit seit Kinetik-Start (min)")
    ax.set_xlabel("Ist-Druck (ITV-Monitor), pro Kinetik-Intervall gemittelt  [bar]")
    ax.set_ylabel("Absorption A500  (Biowave II)")
    ax.set_xlim(left=-0.3)
    if args.ylim:
        ax.set_ylim(*args.ylim)
    ax.grid(True, alpha=0.3)
    ax.set_title(title or f"Kollaps-Fit  --  {phot.name}")
    ax.text(0.02, 0.42,
            f"dP = {fit['dp']:.2f} bar   R$^2$ = {fit['r2']:.3f}   n = {fit['n']}\n"
            f"A: {fit['a_high']:.3f} -> {fit['a_low']:.3f}  ({fit['drop_pct']:.0f} %)",
            transform=ax.transAxes, fontsize=8.5, va="bottom", color="#444444",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc", alpha=0.85))
    ax.legend(loc="lower left", fontsize=8, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(out)
    print(f"\ngespeichert: {out}")
    print(f"gespeichert: {csv_out}")


if __name__ == "__main__":
    main()
