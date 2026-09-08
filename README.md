# hydrostatic-pressure-scripts

⚠ **Achtung Attribution:** Diese README + alle Testläufe/Verifizierungen unten stammen unverändert aus
**Sebis** Repo — „getestet"/„verifiziert" bezieht sich auf **Sebis** Rechner/Bench, nicht auf Max'.
Max muss das komplette Setup (arduino-cli-Installation, Board/Prozessor/Port, erster Flash, erster
`capture.py`-Lauf) auf seinem **eigenen** Rechner einmal selbst durchlaufen — nichts davon ist für sein
Setup bereits verifiziert (Port-Name, Toolchain-Installation etc. können abweichen).

Bench-Skripte für den Druckregler des Hydrostatic-Pressure-Rigs
(SMC **ITV0050-2CL**, angesteuert von einem **Arduino Nano** über einen
**MCP4725 / GY-4725** DAC). Kontext + Verkabelung: [[Hydrostatic-Pressure-Setup-Overview]]
im Second Brain.

## Was hier liegt

| Pfad | Inhalt |
|---|---|
| `hold_test_nano.md` etc. | die Notiz-Fassung: Prosa + Codeblock (das ist die Quelle für den Vault) |
| `sketches/<name>/<name>.ino` | dieselben Sketches als kompilierbare Arduino-Ordner |
| `capture.py` | Serial-Logger für den **Nano/ITV**: schreibt CSV nach `data/`, zeigt Soll-/Ist-Druck in bar |
| `photometer_capture.py` | Serial-Logger für das **WPA Biowave II** (115200 8N1): Rohmitschnitt + geparste CSV nach `data/photometer/` |
| `data/*.csv` | Nano/ITV-Messläufe, roh in Volt |
| `data/photometer/*` | Biowave-II-Mitschnitte (`.txt` roh, `.csv` geparst: `time,label,value`) |
| `plot_sweep.py` | Grafik Solldruck/Ist-Druck aus einer `data/*.csv` (von Max, 2026-08-24) — `python3 plot_sweep.py data/itv-<timestamp>.csv`, Output nach `assets/Hydrostatic-Pressure-Setup/sweeps/druckverlauf_<csv-stem>.png`; `--out`/`--title` optional |
| `plot_od_vs_pressure.py` | A₅₀₀ gegen den pro Kinetik-Intervall gemittelten Ist-Druck (Kollaps-Kennlinie), mit linear interpoliertem Onset/P50 — `python3 plot_od_vs_pressure.py <phot-csv> --itv <itv-csv> --skip N --offset S` |
| `fit_collapse_pressure.py` | wie `plot_od_vs_pressure.py`, aber fittet an den Hochramp-Ast eine fallende 4-Parameter-Boltzmann-Sigmoide und gibt den **Wendepunkt als Kollapsdruck P50** (± 1σ) aus, dazu dP / Onset / P95 / R². Diagramm + Parameter-CSV nach `assets/Hydrostatic-Pressure-Setup/sweeps/kollapsfit_<phot-stem>.*`. `--preset laufD` belegt Dateien/skip/offset vor; sonst `<phot-csv> --itv <itv-csv> --skip N --offset S` |

Die `.md`-Codeblöcke und die `.ino`-Dateien werden von Hand synchron gehalten — beim Ändern
**beide** anfassen.

## Die vier Sketches

| Sketch | Bedienung | CSV-Spalten |
|---|---|---|
| `hold_test_nano` | eine Spannung eintippen, wird gehalten; jederzeit neue Zahl; `stop` → 0 V | `t_s,soll_v,loopback_v,monitor_v` |
| `step_hold_test_nano` | Haltezeit + kommagetrennte Spannungsliste (≤50) | `+ step_idx` |
| `full_sweep_nano` | Schrittgröße + Haltezeit, fährt 0→5→0 V automatisch | `+ dir` (up/down → Hysterese) |
| `sweep_up_nano` | wie `full_sweep_nano`, aber nur 0→5 V, **keine Rückfahrt** (von Max, 2026-08-24) | `+ dir` (immer `up`) |

Alle vier: I²C-DAC auf `0x60`, `A1` = DAC-Loopback, `A0` = ITV-Monitor, 10 Hz, 115200 Baud,
`setVoltage(0.0)` im `setup()` (Reset = drucklos).

## Toolchain (von Sebi verifiziert 2026-08-23, auf seinem Rechner)

```bash
brew install arduino-cli          # Core arduino:avr war schon da (von der IDE)
arduino-cli compile -b arduino:avr:nano:cpu=atmega328 -u -p /dev/cu.usbserial-1110 sketches/step_hold_test_nano
python3 capture.py                # Port wird automatisch gefunden
```

⚠ **Prozessor = `atmega328`, nicht `atmega328old`.** Der CH340-Klon-Nano hier hat trotz Klon-Herkunft
den **neuen** Bootloader. Falsche Wahl → `not in sync: resp=0x9e`, zehn Versuche, Abbruch.
In der IDE entsprechend *Tools → Processor → ATmega328P* (ohne „Old Bootloader").

`arduino-cli board list` zeigt den Port, aber `Unknown` als Board — der CH340 identifiziert den
seriellen Chip, nicht das Board. Board/Bootloader lassen sich nicht auslesen, nur ausprobieren.

## capture.py

Ersetzt den Serial Monitor (der kann **nicht** in eine Datei loggen — weder IDE 1.x noch 2.x).
Bidirektional: Eingaben werden an den Nano durchgereicht, `\r` → `\n` übersetzt.

- Prosa-Zeilen des Sketches → nur Terminal; Datenzeilen → Terminal **und** CSV.
- Jede Header-Zeile (`t_s,…`) startet eine neue Datei `data/itv-<zeitstempel>.csv` — ein Lauf = eine Datei.
- Die CSV bleibt **roh in Volt**. Die bar-Umrechnung ist nur Anzeige, damit eine spätere
  Neukalibrierung alte Läufe nicht still entwertet.
- Terminal zeigt: `soll` (V und bar), `ist` (V und bar), `d` (Ist−Soll in bar, = Einschwing-Indikator),
  `loop` (V).

Kalibrierkonstanten stehen oben in der Datei: `P_FULL_BAR = 9.0`, `MONITOR_V_ZERO = 1.0`,
`MONITOR_V_MAX = 5.0`. Umrechnung: **V = bar × 5/9**, also 8 bar = 4,444 V.

⚠ Öffnet `/dev/cu.*`, löst also **keinen** Reset aus — ein laufender Sketch wird nicht unterbrochen,
aber es erscheint auch kein Prompt, wenn der Sketch schon wartet. Ctrl-C beendet nur den Logger;
der Nano hält seine letzte Spannung, bis man Reset drückt.

## photometer_capture.py

Loggt den „Print"-Datenstrom des **WPA Biowave II** (kein Fernsteuerkanal, nur
Datenexport). Voraussetzung am Gerät: **Auto-Print On**. Anschluss ist USB
Type-B → am Mac als `/dev/cu.usbserial-*`.

- **Serielle Parameter fest: 115200 Baud, 8N1, kein Handshake.** Empirisch
  gefunden 2026-09-01 (Baud-/Paritäts-Sweep, s. [[Hydrostatic-Pressure-Setup-Testprotokoll]]),
  im Manual nicht sauber dokumentiert. Wie bei `capture.py` wird die Rate auf dem
  **offenen** fd gesetzt (`stty -f` verwirft sie auf macOS beim Schließen).
- WPAs „Print via Computer"-Protokoll: jede `$?C`-Zeile endet auf einem
  Type-Code — **`1024` = echter Messwert**, `0`/Spaltenbreite = Header/Metadaten.
  Zwei Layouts, beide unterstützt:
  - **Single Wavelength:** Block pro Messung `$PCT` / `$PC "<uhr>" 0` /
    `$PC "<label>" 0` / `$PC "<wert>" 1024` / `$PET`. `<label>` = `"Reference"`
    oder Messpunkt-Nr. → CSV `uhr,label,wert`.
  - **Kinetics:** Zeitreihe kommt **am Laufende** als `$XC`-Paarblock nach
    `$XCD "TN"` — `$XC "hh:mm:ss" 1024` + `$XC "<wert>" 1024` je Punkt → CSV
    `verstrichene_zeit,punktindex,wert`. Kinetics-Lauf also **bis zum Ende**
    laufen lassen, sonst kommt nichts.
- Pro Aufruf zwei Dateien in `data/photometer/`:
  `photometer-<zeitstempel>.txt` (roher Protokollmitschnitt, verlustfrei — die
  maßgebliche Quelle) und `photometer-<zeitstempel>.csv` (`time,label,value`,
  best effort geparst). Terminal zeigt jede Messung live.
- `python3 photometer_capture.py` (Port wird gesucht) oder mit Port als Argument.
  Ctrl-C beendet den Logger; das Photometer läuft davon unberührt weiter.

## Änderungen 2026-08-23

- **`holdS`-Validierung** in `step_hold_test_nano` + `full_sweep_nano` ergänzt (`.md` und `.ino`).
  Vorher wurde nur `stepSize` geprüft; eine unlesbare Haltezeit ergab `toFloat() = 0` → `holdMs = 0`
  → alle Stufen ohne Verweilzeit, d. h. Vollausschlag in Millisekunden ohne eine einzige Messzeile.
  Genau das ist beim ersten Versuch passiert, weil die Baudrate nicht stimmte und der Nano
  Zeichensalat empfing.
- **`capture.py` Baudrate-Bug behoben.** Vorher wurde die Rate per `stty -f` gesetzt; macOS verwirft
  die Einstellung beim Schließen des Ports, sodass danach mit 9600 statt 115200 gelesen wurde
  (Symptom: Zeichensalat). Jetzt via `termios.tcsetattr` auf dem **offenen** fd. Am Port verifiziert:
  vorher 9600, nachher 115200.
- **Laufzeit-Beispiele in `full_sweep_nano.md` korrigiert** — sie waren durchgehend das Doppelte der
  im selben Absatz angegebenen Formel (0,1V/3s ist ~5 min, nicht ~10).

### Noch offen (aus dem Review, bewusst nicht gemacht)

- Die Warteschleifen leeren den seriellen Eingangspuffer nicht. Was während eines Laufs getippt wird,
  landet im nächsten Prompt. Fix wäre `while (Serial.available()) Serial.read();` vor der ersten Frage.
- Schrittgrößen, die 5,0 nicht teilen, erreichen den Endwert nie (0,7 V → Schluss bei 4,9 V), ohne Hinweis.
- **Der Loopback ist ratiometrisch** und kann den Fehler, der zählt, prinzipiell nicht sehen: DAC und
  ADC hängen beide an derselben 5-V-Schiene, ein Absacken auf 4,7 V kürzt sich heraus und `loopback_v`
  liest weiter „perfekt", während der ITV real ~6 % weniger Druck bekommt. Der Loopback ist eine
  Durchgangsprüfung, keine Kalibrierung. Echte Abhilfe = LM4040-Referenz (steht in der BOM).

## Erster Lauf (von Sebi): 2026-08-23, 0–8 bar

`data/itv-20260823-182001.csv` — 17 Stufen à 5 s, 850 Messpunkte, `step_hold_test_nano`.
Auswertung als Grafik: https://claude.ai/code/artifact/23af574a-caa6-42c8-8910-dfd882478226

- Maximaler Fehler **0,135 bar** über 0–8 bar; der Rest ist ein nahezu konstanter Offset.
- Ursache des Offsets: der Monitor-Nullpunkt liegt bei **1,06 V**, nicht 1,00 V. Betrifft nur die
  Anzeige, nicht den Sollwert.
- DAC-Loopback ±4,3 mV → unter 1 ADC-LSB (4,9 mV). I²C-Kette sauber.
- **Keine Sättigung bei 8 bar** — die Hausluft trägt den vollen Bereich. Damit ist die offene Frage
  „reale Bench-Druck?" aus der Projektnotiz beantwortet.
- Anstiegszeit **≤ 0,4 s** auf jeder Stufe → die 5 s Haltezeit sind ~10× mehr als nötig.
- Monitor-Rauschen wächst mit dem Druck: 19 mV (drucklos) → 108 mV (8 bar), ≈ 0,24 bar. Relevant,
  falls der Monitor als Einschwing-Detektor (`dP/dt → 0`) dienen soll — die Schwelle muss über dem
  Rauschen liegen.
- ⚠ Alle bar-Werte hängen an der angenommenen Kalibrierung (0–5 V = 0–9 bar, Monitor 1–5 V). Gegen ein
  Referenzmanometer ist das **nicht** geprüft; die Monitor-Spezifikation erlaubt ±6 % FS absolut.
  Die *Tracking*-Aussage bleibt davon unberührt, die Absolutachse nicht.
