# hold_test_fast — Pico, Sprungantwort mit 0.05s-Sampling

MicroPython-Skript für den **Pico** (s. [[Hydrostatic-Pressure-Setup-Overview]]): wie [[hold_test]], aber für die **Sprungantwort-Messung** gedacht — feste **5s Messdauer bei 0.05s-Intervall** (statt unbegrenzt bei 1s), danach automatischer Reset auf 0V und Programmende (kein Ctrl+C nötig, funktioniert aber weiterhin als Not-Aus). Damit wurde die Einschwingzeit des ITV0050 erstmals präzise gemessen (~0.1–0.2s, s. Overview).

**Verkabelung:** wie [[sweep_test_itv]] — GY-4725 VOUT → Pico GP26 + ITV Pin 2; ITV Pin 4 → Pico GP27.

```python
from machine import Pin, I2C, ADC
import time

i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=100000)
DAC_ADDR = 0x60           # Standardadresse GY-4725
loopback = ADC(Pin(26))   # GY-4725 VOUT -> Pico GP26
monitor = ADC(Pin(27))    # ITV Pin 4 (schwarz) -> Pico GP27
V_SUPPLY = 3.3
V_CAP = 2.0                # Sicherheits-Cap, s. Overview-Notiz -- unveraendert uebernommen
MAX_CODE = int((V_CAP / V_SUPPLY) * 4095)
P_MAX = 9.0                 # bar, entspricht 0.9 MPa
DURATION_S = 5.0            # Gesamtmessdauer, danach automatischer Stopp
INTERVAL_S = 0.05           # Abstand zwischen Log-Zeilen
LOGFILE = "hold_test_fast_log.csv"

def set_voltage(v):
    v = max(0.0, min(V_CAP, v))          # harter Software-Cap
    code = int((v / V_SUPPLY) * 4095)
    code = min(code, MAX_CODE)
    hi = (code >> 8) & 0x0F
    lo = code & 0xFF
    i2c.writeto(DAC_ADDR, bytes([hi, lo]))
    return v

def read_loopback():
    return loopback.read_u16() * V_SUPPLY / 65535

def read_monitor():
    return monitor.read_u16() * V_SUPPLY / 65535

def monitor_to_bar(v_mon):
    return (v_mon - 1) / 4 * P_MAX

target = float(input("Zielspannung halten (0.0-{}): ".format(V_CAP)))
target = set_voltage(target)
print("Halte", target, "V fuer", DURATION_S, "s, logge alle", INTERVAL_S, "s nach", LOGFILE)
print("Danach automatisch 0V. Abbrechen vorzeitig mit Ctrl+C (setzt ebenfalls auf 0V zurueck)")

f = open(LOGFILE, "w")
f.write("t_s,soll_v,loopback_v,monitor_v,druck_bar\n")

t0 = time.ticks_ms()
t_s = 0.0
try:
    while t_s < DURATION_S:
        t_s = time.ticks_diff(time.ticks_ms(), t0) / 1000
        lb = read_loopback()
        mon = read_monitor()
        bar = monitor_to_bar(mon)
        line = "{:.3f},{:.3f},{:.3f},{:.3f},{:.3f}".format(t_s, target, lb, mon, bar)
        print(line)
        f.write(line + "\n")
        f.flush()
        time.sleep(INTERVAL_S)
    print("Messdauer erreicht nach", round(t_s, 2), "s. Log gespeichert in", LOGFILE)
except KeyboardInterrupt:
    print("Vorzeitig gestoppt nach", round(t_s, 2), "s. Log gespeichert in", LOGFILE)
finally:
    f.close()
    set_voltage(0.0)
```
