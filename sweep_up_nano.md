# sweep_up_nano — Nano, einmaliger 0–5V-Sweep nur hoch (keine Rückfahrt)

Arduino-Sketch für den **Nano** (s. [[Hydrostatic-Pressure-Setup-Overview]]): fährt einen einmaligen Sweep **0V → 5V** in frei einstellbarer Schrittgröße, hält jeden Schritt eine frei einstellbare Zeit und loggt dabei alle 0,1s Soll-, Loopback- (A1) und Monitor-Spannung (A0) — wie [[full_sweep_nano]], aber **ohne die Rückfahrt** 5V→0V. Für Fälle gedacht, wo nur die Hochlauf-Kennlinie interessiert und die zweite Hälfte (Hysterese-Check) nicht gebraucht wird — halbiert die Laufzeit gegenüber `full_sweep_nano` bei gleicher Schrittgröße/Haltezeit.

**Verkabelung:** wie in der Overview-Notiz („Verkabelung (Nano-Zielaufbau)") — GY-4725 VOUT → Nano A4/A5 (I2C) + ITV Pin 2 (weiß) + zusätzlich Nano A1 (Loopback); ITV Pin 4 (schwarz, Monitor-Output) → Nano A0 direkt.

**Bedienung über den Serial Monitor (115200 Baud, Zeilenende „Newline"):**
1. Schrittgröße in V eingeben (z. B. `0.1`)
2. Haltezeit pro Schritt in Sekunden eingeben (z. B. `3`)
3. Läuft automatisch bis 5V hoch, danach automatisch 0V (direkt, nicht gestuft geloggt) und zurück zur ersten Frage — für einen neuen Lauf einfach wieder Werte eingeben, kein Reset/Neu-Flashen nötig
4. Ein physischer Reset setzt ebenfalls automatisch auf 0V zurück (`setVoltage(0.0)` in `setup()`)

**Laufzeit-Faustregel:** Anzahl Schritte ≈ `5 / Schrittgröße` (halb so viele wie bei `full_sweep_nano`), Gesamtdauer ≈ Anzahl Schritte × Haltezeit. Beispiel 0,1V/3s → 51 Schritte → ~2,5 Minuten.

**Flashen:** die Sketches liegen als kompilierbare Ordner unter `sketches/`. Board = **Arduino Nano**, Prozessor = **ATmega328P** (NICHT „Old Bootloader" — s. `README.md`). Per Terminal:

```bash
arduino-cli compile -b arduino:avr:nano:cpu=atmega328 -u -p /dev/cu.usbserial-130 sketches/sweep_up_nano
```

**Loggen:** `capture.py` benutzen, wie bei den anderen Sketches:

```bash
python3 capture.py
```

**Grafik:** die CSV lässt sich direkt mit `plot_sweep.py` auswerten (`dir` steht immer auf `up`):

```bash
python3 plot_sweep.py data/itv-<timestamp>.csv
```

**Für die Arduino IDE:** Code unten in ein neues Sketch (`.ino`) kopieren, oder in einen gleichnamigen Ordner legen (Arduino verlangt Ordner- = Dateiname).

```cpp
#include <Wire.h>

const uint8_t DAC_ADDR = 0x60;     // Standardadresse GY-4725
const float V_SUPPLY = 5.0;        // Nano-Versorgung = DAC-Referenz (GY-4725 VCC -> Nano 5V)
const int LOOPBACK_PIN = A1;       // GY-4725 VOUT -> Nano A1
const int MONITOR_PIN = A0;        // ITV Pin 4 (schwarz) -> Nano A0
const unsigned long INTERVAL_MS = 100;

void setVoltage(float v) {
  v = max(0.0f, min(V_SUPPLY, v));
  uint16_t code = (uint16_t)((v / V_SUPPLY) * 4095);
  uint8_t hi = (code >> 8) & 0x0F;   // obere Nibble bleibt 0 (Fast-Mode-Kennung)
  uint8_t lo = code & 0xFF;
  Wire.beginTransmission(DAC_ADDR);
  Wire.write(hi);
  Wire.write(lo);
  Wire.endTransmission();
}

float readLoopback() {
  return analogRead(LOOPBACK_PIN) * V_SUPPLY / 1023.0;
}

float readMonitor() {
  return analogRead(MONITOR_PIN) * V_SUPPLY / 1023.0;
}

String readLine() {
  while (!Serial.available()) {}
  String line = Serial.readStringUntil('\n');
  line.trim();
  return line;
}

void runStep(float v, const char* dir, unsigned long holdMs, unsigned long t0) {
  setVoltage(v);
  unsigned long stepStart = millis();
  unsigned long lastSample = 0;
  while (millis() - stepStart < holdMs) {
    if (millis() - lastSample >= INTERVAL_MS) {
      lastSample = millis();
      Serial.print((millis() - t0) / 1000.0, 2);
      Serial.print(",");
      Serial.print(dir);
      Serial.print(",");
      Serial.print(v, 3);
      Serial.print(",");
      Serial.print(readLoopback(), 3);
      Serial.print(",");
      Serial.println(readMonitor(), 3);
    }
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  setVoltage(0.0);
}

void loop() {
  Serial.println("Schrittgroesse in V eingeben (z.B. 0.1):");
  float stepSize = readLine().toFloat();
  if (stepSize <= 0.0) {
    Serial.println("Ungueltige Schrittgroesse, nochmal von vorne.");
    return;
  }

  Serial.println("Haltezeit pro Schritt in s eingeben (z.B. 3):");
  float holdS = readLine().toFloat();
  if (holdS <= 0.0) {
    Serial.println("Ungueltige Haltezeit, nochmal von vorne.");
    return;
  }
  unsigned long holdMs = (unsigned long)(holdS * 1000);

  int numSteps = (int)round(V_SUPPLY / stepSize);

  Serial.print("Sweep 0V->");
  Serial.print(V_SUPPLY);
  Serial.print("V (nur hoch, keine Rueckfahrt), Schrittgroesse ");
  Serial.print(stepSize, 3);
  Serial.print("V, je ");
  Serial.print(holdS, 2);
  Serial.println("s:");
  Serial.println("t_s,dir,soll_v,loopback_v,monitor_v");

  unsigned long t0 = millis();

  for (int i = 0; i <= numSteps; i++) {
    float v = min((float)i * stepSize, V_SUPPLY);
    runStep(v, "up", holdMs, t0);
  }

  setVoltage(0.0);
  Serial.println("Sweep hoch fertig, 0V gesetzt.");
  Serial.println();
}
```
