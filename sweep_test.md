# sweep_test — Pico, DAC allein (Phase 1)

MicroPython-Skript für den **Pico**, Phase 1 (s. [[Hydrostatic-Pressure-Setup-Overview]]): steuert nur den GY-4725 (MCP4725-DAC) an, noch **ohne** den Pressure Controller (ITV0050). Interaktiv über die REPL: entweder eine feste Spannung (0.0–3.3V) setzen oder `sweep` für einen automatischen 0→3.3V→0V-Durchlauf, jeweils mit Readback über den DAC-eigenen VOUT-Loopback (Pico GP26).

**Verkabelung:** GY-4725 VOUT → Pico GP26.

```python
from machine import Pin, I2C, ADC
import time

i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=100000)
DAC_ADDR = 0x60          # Standardadresse GY-4725
readback = ADC(Pin(26))  # GY-4725 VOUT -> Pico GP26
V_SUPPLY = 3.3

def set_voltage(v):
    v = max(0.0, min(V_SUPPLY, v))
    code = int((v / V_SUPPLY) * 4095)
    hi = (code >> 8) & 0x0F   # nur die oberen 4 Datenbits, obere Nibble bleibt 0
    lo = code & 0xFF          # untere 8 Datenbits direkt
    i2c.writeto(DAC_ADDR, bytes([hi, lo]))

def read_voltage():
    return readback.read_u16() * V_SUPPLY / 65535

while True:
    cmd = input("Spannung (0.0-3.3) oder 'sweep': ")
    if cmd == "sweep":
        steps = list(range(0, 101)) + list(range(100, -1, -1))
        for i in steps:
            set_voltage(i * V_SUPPLY / 100)
            time.sleep(0.05)
            print(i, "gemessen:", read_voltage())
    else:
        set_voltage(float(cmd))
        time.sleep(0.05)
        print("gemessen:", read_voltage())
```
