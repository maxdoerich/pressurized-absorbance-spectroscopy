# step_hold_test_nano — Nano, Haltezeit + freie Druckliste eingeben

Arduino-Sketch für den **Nano** (s. [[Hydrostatic-Pressure-Setup-Overview]]): über Serial zuerst eine Haltezeit pro Stufe eingeben, danach eine **beliebig lange, kommagetrennte Liste von Zielspannungen** (z. B. `0.1, 0.2, 0.3, 0.4, 0.5`) — das Skript fährt die Stufen automatisch nacheinander an, hält jede für die eingegebene Zeit und loggt alle 0,1s. Nano-Äquivalent zu [[step_hold_test]] (Pico), aber mit frei eingebbarer Stufenliste statt fest im Code hinterlegter `STEPS`, und Eingabe/Ausgabe in Volt statt bar (wie [[hold_test_nano]]).

**Verkabelung:** wie in der Overview-Notiz („Verkabelung (Nano-Zielaufbau)") — GY-4725 VOUT → Nano A4/A5 (I2C) + ITV Pin 2 (weiß) + zusätzlich Nano A1 (Loopback); ITV Pin 4 (schwarz, Monitor-Output) → Nano A0 direkt.

**Bedienung über den Serial Monitor (115200 Baud, Zeilenende „Newline"):**
1. Haltezeit pro Stufe in Sekunden eingeben (z. B. `5`)
2. Zielspannungen kommagetrennt eingeben (z. B. `0.1, 0.2, 0.3, 0.4, 0.5`) — Leerzeichen um die Kommas sind egal, bis zu 50 Werte
3. Läuft automatisch alle Stufen durch, danach automatisch 0V und zurück zur ersten Frage — für einen neuen Lauf einfach wieder Haltezeit + Liste eingeben, kein Reset/Neu-Flashen nötig
4. Ein physischer Reset setzt ebenfalls automatisch auf 0V zurück (`setVoltage(0.0)` in `setup()`)

**Flashen (von Sebi getestet 2026-08-23, auf seinem Rechner — Max noch nicht auf eigenem Setup verifiziert):** die Sketches liegen als kompilierbare Ordner unter `sketches/`.
Board = **Arduino Nano**, Prozessor = **ATmega328P** (NICHT „Old Bootloader" — der CH340-Nano hier hat
den neuen Bootloader; mit `Old Bootloader` bricht der Upload mit `not in sync: resp=0x9e` ab).
Per Terminal:

```bash
arduino-cli compile -b arduino:avr:nano:cpu=atmega328 -u -p /dev/cu.usbserial-1110 sketches/step_hold_test_nano
```

**Loggen:** statt des Serial Monitors `capture.py` benutzen — schreibt eine CSV nach `data/` und zeigt
Soll-/Ist-Druck in bar an (s. `README.md`):

```bash
python3 capture.py
```

**Für die Arduino IDE:** Code unten in ein neues Sketch (`.ino`) kopieren, oder in einen gleichnamigen Ordner legen (Arduino verlangt Ordner- = Dateiname).

```cpp
#include <Wire.h>

const uint8_t DAC_ADDR = 0x60;     // Standardadresse GY-4725
const float V_SUPPLY = 5.0;        // Nano-Versorgung = DAC-Referenz (GY-4725 VCC -> Nano 5V)
const int LOOPBACK_PIN = A1;       // GY-4725 VOUT -> Nano A1
const int MONITOR_PIN = A0;        // ITV Pin 4 (schwarz) -> Nano A0
const unsigned long INTERVAL_MS = 100;
const int MAX_STEPS = 50;

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

int parseSteps(String input, float steps[], int maxSteps) {
  int count = 0;
  int start = 0;
  while (start <= (int)input.length() && count < maxSteps) {
    int commaIdx = input.indexOf(',', start);
    String token = (commaIdx == -1) ? input.substring(start) : input.substring(start, commaIdx);
    token.trim();
    if (token.length() > 0) steps[count++] = token.toFloat();
    if (commaIdx == -1) break;
    start = commaIdx + 1;
  }
  return count;
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  setVoltage(0.0);
}

void loop() {
  Serial.println("Haltezeit pro Stufe in s eingeben:");
  float holdS = readLine().toFloat();
  if (holdS <= 0.0) {
    Serial.println("Ungueltige Haltezeit, nochmal von vorne.");
    return;
  }

  Serial.println("Zielspannungen eingeben, kommagetrennt (z.B. 0.1, 0.2, 0.3):");
  float steps[MAX_STEPS];
  int stepCount = parseSteps(readLine(), steps, MAX_STEPS);

  if (stepCount == 0) {
    Serial.println("Keine gueltigen Werte erkannt, nochmal von vorne.");
    return;
  }

  Serial.print("Fahre ");
  Serial.print(stepCount);
  Serial.print(" Stufen, je ");
  Serial.print(holdS, 2);
  Serial.println("s:");
  Serial.println("t_s,step_idx,soll_v,loopback_v,monitor_v");

  unsigned long t0 = millis();
  unsigned long holdMs = (unsigned long)(holdS * 1000);
  for (int i = 0; i < stepCount; i++) {
    setVoltage(steps[i]);
    unsigned long stepStart = millis();
    unsigned long lastSample = 0;
    while (millis() - stepStart < holdMs) {
      if (millis() - lastSample >= INTERVAL_MS) {
        lastSample = millis();
        Serial.print((millis() - t0) / 1000.0, 2);
        Serial.print(",");
        Serial.print(i);
        Serial.print(",");
        Serial.print(steps[i], 3);
        Serial.print(",");
        Serial.print(readLoopback(), 3);
        Serial.print(",");
        Serial.println(readMonitor(), 3);
      }
    }
  }

  setVoltage(0.0);
  Serial.println("Alle Stufen durchlaufen, 0V gesetzt.");
  Serial.println();
}
```
