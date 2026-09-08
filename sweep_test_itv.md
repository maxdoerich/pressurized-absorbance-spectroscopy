# sweep_test_itv — Pico, DAC + ITV0050 (Phase 2, vorgezogener Test)

MicroPython-Skript für den **Pico**, vorgezogener Phase-2-Test (s. [[Hydrostatic-Pressure-Setup-Overview]]): steuert den GY-4725 (MCP4725-DAC) an, dessen VOUT jetzt an ITV Pin 2 (Input-Signal) hängt. Ausgabe per **Sicherheits-Cap auf 2.0V** hart begrenzt (Pico läuft nativ auf 3.3V, 2.0V-Cap war der bewusst konservative erste Test, s. Overview). Zusätzlicher zweiter ADC liest den ITV-eigenen Monitor-Output (Ist-Druck) mit. Bedienung interaktiv: feste Spannung setzen, `step` (+0.1V-Schritte) oder `zero`.

**Verkabelung:** GY-4725 VOUT → Pico GP26 (Loopback) **und** → ITV Pin 2 (weiß); ITV Pin 4 (schwarz, Monitor-Output) → Pico GP27.

```python
from machine import Pin, I2C, ADC
import time

i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=100000)
DAC_ADDR = 0x60           # Standardadresse GY-4725
loopback = ADC(Pin(26))   # GY-4725 VOUT -> Pico GP26 (DAC-Ausgang, elektronisch)
monitor = ADC(Pin(27))    # ITV Pin 4 (schwarz) -> Pico GP27 (Ist-Druck laut ITV)
V_SUPPLY = 3.3
V_CAP = 2.0                # Sicherheits-Cap fuer ITV Pin 2 Input, s. Overview-Notiz
MAX_CODE = int((V_CAP / V_SUPPLY) * 4095)   # ~2482
STEP = 0.1                 # V pro "step"-Aufruf

_current = 0.0

def set_voltage(v):
    v = max(0.0, min(V_CAP, v))          # harter Software-Cap, unabhaengig vom Aufrufer
    code = int((v / V_SUPPLY) * 4095)
    code = min(code, MAX_CODE)
    hi = (code >> 8) & 0x0F              # obere Nibble bleibt 0 (Fast-Mode-Kennung)
    lo = code & 0xFF
    i2c.writeto(DAC_ADDR, bytes([hi, lo]))
    return v

def read_loopback():
    return loopback.read_u16() * V_SUPPLY / 65535

def read_monitor():
    return monitor.read_u16() * V_SUPPLY / 65535

def report():
    print("soll:", round(_current, 3),
          " loopback:", round(read_loopback(), 3),
          " monitor:", round(read_monitor(), 3))

set_voltage(0.0)
report()

while True:
    cmd = input("Spannung (0.0-{}), 'step' (+{}V) oder 'zero': ".format(V_CAP, STEP))
    if cmd == "step":
        _current = set_voltage(_current + STEP)
    elif cmd == "zero":
        _current = set_voltage(0.0)
    else:
        _current = set_voltage(float(cmd))
    time.sleep(0.05)
    report()
```
