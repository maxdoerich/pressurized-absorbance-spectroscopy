# hold_test_nano — Nano, Zielspannung eingeben + kontinuierlich auslesen (0,1s)

Arduino-Sketch für den **Nano** (s. [[Hydrostatic-Pressure-Setup-Overview]]): über Serial eine Zielspannung in **Volt** eingeben, das Skript hält sie und gibt alle **0,1s** Soll-Spannung, DAC-Loopback (A1) und ITV-Monitor-Output (A0) aus, bis das Programm gestoppt wird. Nano-Äquivalent zu [[hold_test]] (Pico), Intervall wie [[hold_test_fast]] (0,1s statt 1s), Loopback-Readback wie [[nano_dac_test]] (A1).

**Verkabelung:** wie in der Overview-Notiz („Verkabelung (Nano-Zielaufbau)") — GY-4725 VOUT → Nano A4/A5 (I2C) + ITV Pin 2 (weiß) + zusätzlich Nano A1 (Loopback); ITV Pin 4 (schwarz, Monitor-Output) → Nano A0 direkt.

**Bedienung über den Serial Monitor (115200 Baud, Zeilenende „Newline"):**
- Zahl eingeben (z. B. `2.5`) → setzt diese Spannung, Auslesen läuft ab sofort alle 0,1s
- Neue Zahl jederzeit eingeben → wechselt die Zielspannung ohne Unterbrechung des Loggings
- `stop` eingeben → setzt 0V und pausiert das Auslesen (Programm läuft weiter, wartet auf neue Eingabe) — das ist das „Stoppen" per Software, ein Reset per Taster/Neu-Flashen setzt ebenfalls automatisch auf 0V zurück (`setVoltage(0.0)` in `setup()`)

**Flashen (von Sebi getestet 2026-08-23, auf seinem Rechner — Max noch nicht auf eigenem Setup verifiziert):** die Sketches liegen als kompilierbare Ordner unter `sketches/`.
Board = **Arduino Nano**, Prozessor = **ATmega328P** (NICHT „Old Bootloader" — der CH340-Nano hier hat
den neuen Bootloader; mit `Old Bootloader` bricht der Upload mit `not in sync: resp=0x9e` ab).
Per Terminal:

```bash
arduino-cli compile -b arduino:avr:nano:cpu=atmega328 -u -p /dev/cu.usbserial-1110 sketches/hold_test_nano
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

float targetV = 0.0;
bool running = false;
unsigned long lastRead = 0;

void setVoltage(float v) {
  v = max(0.0f, min(V_SUPPLY, v));
  uint16_t code = (uint16_t)((v / V_SUPPLY) * 4095);
  uint8_t hi = (code >> 8) & 0x0F;   // obere Nibble bleibt 0 (Fast-Mode-Kennung)
  uint8_t lo = code & 0xFF;
  Wire.beginTransmission(DAC_ADDR);
  Wire.write(hi);
  Wire.write(lo);
  Wire.endTransmission();
  targetV = v;
}

float readLoopback() {
  return analogRead(LOOPBACK_PIN) * V_SUPPLY / 1023.0;
}

float readMonitor() {
  return analogRead(MONITOR_PIN) * V_SUPPLY / 1023.0;
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  setVoltage(0.0);
  Serial.print("Zielspannung eingeben (0.0-");
  Serial.print(V_SUPPLY);
  Serial.println("), 'stop' haelt an und setzt 0V:");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      if (cmd == "stop") {
        setVoltage(0.0);
        running = false;
        Serial.println("Gestoppt, 0V gesetzt. Neue Spannung eingeben zum Fortsetzen:");
      } else {
        setVoltage(cmd.toFloat());
        running = true;
        Serial.println("t_s,soll_v,loopback_v,monitor_v");
      }
    }
  }

  if (running && millis() - lastRead >= INTERVAL_MS) {
    lastRead = millis();
    Serial.print(millis() / 1000.0, 1);
    Serial.print(",");
    Serial.print(targetV, 3);
    Serial.print(",");
    Serial.print(readLoopback(), 3);
    Serial.print(",");
    Serial.println(readMonitor(), 3);
  }
}
```
