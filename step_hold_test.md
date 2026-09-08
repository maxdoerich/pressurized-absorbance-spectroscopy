# step_hold_test — Pico, automatisierter Mehrstufentest

MicroPython-Skript für den **Pico** (s. [[Hydrostatic-Pressure-Setup-Overview]]): fährt automatisiert mehrere Sollspannungs-**Stufen** nacheinander an (Standard: 0.5V, 1.0V, 1.5V), hält jede für eine beim Start abgefragte Haltezeit, loggt `loopback`/`monitor`/Druck alle 0.1s in eine CSV-Datei (`step_hold_test_log.csv`). Realistischerer Ablauf als [[hold_test]]/[[hold_test_fast]] (eine feste Stufe) — bestätigte Kennlinie und Einschwingzeit an einem mehrstufigen Testlauf. Abbruch mit Ctrl+C setzt automatisch auf 0V zurück.

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
INTERVAL_S = 0.1            # Abstand zwischen Log-Zeilen
STEPS = [0.5, 1.0, 1.5]     # Sollspannungen, nacheinander angefahren
LOGFILE = "step_hold_test_log.csv"

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

hold_s = float(input("Haltezeit pro Stufe in s (Stufen: {}): ".format(STEPS)))
print("Fahre Stufen", STEPS, "je", hold_s, "s, logge alle", INTERVAL_S, "s nach", LOGFILE)
print("Abbrechen mit Ctrl+C (setzt danach automatisch auf 0V zurueck)")

f = open(LOGFILE, "w")
f.write("t_s,step_idx,soll_v,loopback_v,monitor_v,druck_bar\n")

t0 = time.ticks_ms()
t_s = 0.0
try:
    for idx, step_v in enumerate(STEPS):
        target = set_voltage(step_v)
        t_step0 = time.ticks_ms()
        t_step = 0.0
        while t_step < hold_s:
            t_s = time.ticks_diff(time.ticks_ms(), t0) / 1000
            t_step = time.ticks_diff(time.ticks_ms(), t_step0) / 1000
            lb = read_loopback()
            mon = read_monitor()
            bar = monitor_to_bar(mon)
            line = "{:.3f},{},{:.3f},{:.3f},{:.3f},{:.3f}".format(t_s, idx, target, lb, mon, bar)
            print(line)
            f.write(line + "\n")
            f.flush()
            time.sleep(INTERVAL_S)
    print("Alle Stufen durchlaufen nach", round(t_s, 2), "s. Log gespeichert in", LOGFILE)
except KeyboardInterrupt:
    print("Vorzeitig gestoppt nach", round(t_s, 2), "s. Log gespeichert in", LOGFILE)
finally:
    f.close()
    set_voltage(0.0)
```
