# nano_dac_test — Arduino-Sketch (Nano + GY-4725)

Test-Sketch für den Nano-Umstieg im Kern-Regelkreis (s. [[Hydrostatic-Pressure-Setup-Overview]]), analog zu [[sweep_test]] für den Pico. Setzt eine feste Spannung am GY-4725 (MCP4725-DAC) oder fährt einen 0→5V→0V-Sweep, liest den Ausgang über Nano-ADC (A1) zurück und meldet den I2C-Übertragungsstatus.

**Verkabelung:**
- GY-4725 VCC → Nano 5V, GND → Nano GND, SDA → Nano A4, SCL → Nano A5
- GY-4725 VOUT → Nano A1 (Readback) — zusätzlich parallel ans Multimeter möglich

**Bedienung über den Serial Monitor (115200 Baud, Zeilenende „Newline"):**
- Zahl eingeben (z. B. `2.5`) → setzt diese Spannung fest
- `sweep` → fährt 0–5V–0V in 101 Schritten, je 50ms, mit Report pro Schritt
- `scan` → I2C-Bus-Scan, zeigt alle antwortenden Geräteadressen

**Für die Arduino IDE:** Code unten in ein neues Sketch (`.ino`) kopieren, oder in einen gleichnamigen Ordner legen (Arduino verlangt Ordner- = Dateiname).

```cpp
#include <Wire.h>

const uint8_t DAC_ADDR = 0x60;   // Standardadresse GY-4725
const float V_SUPPLY = 5.0;      // Nano-Versorgung = DAC-Referenz (GY-4725 VCC -> Nano 5V)
const int LOOPBACK_PIN = A1;     // GY-4725 VOUT -> Nano A1 (zusaetzlich zum Multimeter, zum Gegenchecken)

uint8_t lastI2CStatus = 99;      // 0 = ok, s. Wire.endTransmission()-Rueckgabewerte unten

void setVoltage(float v) {
  v = max(0.0f, min(V_SUPPLY, v));
  uint16_t code = (uint16_t)((v / V_SUPPLY) * 4095);
  uint8_t hi = (code >> 8) & 0x0F;   // obere Nibble bleibt 0 (Fast-Mode-Kennung)
  uint8_t lo = code & 0xFF;
  Wire.beginTransmission(DAC_ADDR);
  Wire.write(hi);
  Wire.write(lo);
  lastI2CStatus = Wire.endTransmission();
}

float readLoopback() {
  return analogRead(LOOPBACK_PIN) * V_SUPPLY / 1023.0;
}

void report(float soll) {
  Serial.print("soll: ");
  Serial.print(soll, 3);
  Serial.print("  gemessen (A1): ");
  Serial.print(readLoopback(), 3);
  Serial.print("  i2c_status: ");
  Serial.println(lastI2CStatus);
  // i2c_status: 0=OK, 1=Daten zu lang, 2=NACK auf Adresse (kein Geraet antwortet),
  // 3=NACK auf Datenbyte, 4=sonstiger Fehler
}

void doScan() {
  Serial.println("I2C-Scan...");
  byte count = 0;
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    byte err = Wire.endTransmission();
    if (err == 0) {
      Serial.print("Geraet gefunden bei 0x");
      Serial.println(addr, HEX);
      count++;
    }
  }
  if (count == 0) Serial.println("Kein Geraet gefunden.");
  else {
    Serial.print(count);
    Serial.println(" Geraet(e) gefunden.");
  }
}

void doSweep() {
  for (int i = 0; i <= 100; i++) {
    float v = i * V_SUPPLY / 100.0;
    setVoltage(v);
    delay(50);
    report(v);
  }
  for (int i = 100; i >= 0; i--) {
    float v = i * V_SUPPLY / 100.0;
    setVoltage(v);
    delay(50);
    report(v);
  }
  Serial.println("Sweep fertig.");
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  setVoltage(0.0);
  Serial.print("Bereit. Spannung (0.0-");
  Serial.print(V_SUPPLY);
  Serial.println("), 'sweep' oder 'scan' eingeben:");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;
    if (cmd == "sweep") {
      doSweep();
    } else if (cmd == "scan") {
      doScan();
    } else {
      float v = cmd.toFloat();
      setVoltage(v);
      delay(50);
      report(v);
    }
  }
}
```
