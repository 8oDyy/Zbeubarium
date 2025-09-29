# hw080.py — Capteur d'humidité de sol HW-080 via AO du HW-103 (LM393)
# MicroPython (Raspberry Pi Pico / Pico W)

import time
import machine

class HW080Soil:
    """
    Lecture analogique du HW-080 via la carte HW-103 (AO -> ADC Pico).
    - adc_pin   : GP26=ADC0, GP27=ADC1, GP28=ADC2 (int ou machine.Pin)
    - power_pin : (optionnel) GPIO qui commande un MOSFET/transistor d'alim.
    - dry_raw   : valeur brute à sec
    - wet_raw   : valeur brute en milieu très humide
    - vref      : tension de référence ADC (Pico ~3.3 V)
    """

    def __init__(self, adc_pin=26, power_pin=None, dry_raw=66000, wet_raw=27859, vref=3.3):
        # Autoriser int ou Pin pour l'ADC
        if isinstance(adc_pin, machine.Pin):
            self.adc = machine.ADC(adc_pin)
        else:
            self.adc = machine.ADC(int(adc_pin))

        self.power = None
        if power_pin is not None:
            self.power = machine.Pin(power_pin, machine.Pin.OUT, value=0)  # 0 = OFF

        # Garantir un ordre cohérent (dry_raw > wet_raw pour HW080)
        d = int(dry_raw); w = int(wet_raw)
        if d <= w:
            d, w = w, d
        self.dry_raw = d
        self.wet_raw = w
        self.vref = float(vref)

    # ----- gestion alim optionnelle -----
    def _power_on(self):
        if self.power:
            self.power.value(1)

    def _power_off(self):
        if self.power:
            self.power.value(0)

    # ----- mesures -----
    def read_raw(self, samples=16, sample_delay_ms=2, warmup_ms=120, median=False):
        """
        Retourne une valeur brute (0..65535).
        - samples : nb d'échantillons
        - median  : True => médiane, False => moyenne
        """
        self._power_on()
        if warmup_ms:
            time.sleep_ms(int(warmup_ms))

        buf = []
        n = max(1, int(samples))
        for _ in range(n):
            buf.append(self.adc.read_u16())
            if sample_delay_ms:
                time.sleep_ms(int(sample_delay_ms))

        self._power_off()

        if median:
            buf.sort()
            mid = len(buf) // 2
            return (buf[mid] if len(buf) % 2 == 1 else (buf[mid-1] + buf[mid]) // 2)
        else:
            return sum(buf) // len(buf)

    def read_voltage(self, **kwargs):
        raw = self.read_raw(**kwargs)
        return raw * self.vref / 65535.0

    def to_percent(self, raw):
        """
        Convertit la valeur brute en % (0..100, borné).
        NOTE: plus c'est humide, plus 'raw' est BAS.
        """
        span = self.dry_raw - self.wet_raw
        if span <= 0:
            return 0.0
        pct = (self.dry_raw - int(raw)) * 100.0 / span
        if pct < 0:
            pct = 0.0
        elif pct > 100:
            pct = 100.0
        return pct

    def read_percent(self, **kwargs):
        raw = self.read_raw(**kwargs)
        return self.to_percent(raw)

    def measure(self, **kwargs):
        """
        Renvoie un dict:
        { "percent": 63.4, "raw": 35120, "voltage": 1.77, "ts": 1699999999 }
        """
        raw = self.read_raw(**kwargs)
        return {
            "percent": round(self.to_percent(raw), 1),
            "raw": raw,
            "voltage": round(raw * self.vref / 65535.0, 3),
            "ts": time.time()
        }

    # ----- helpers calibration -----
    def set_calibration(self, dry_raw=None, wet_raw=None):
        if dry_raw is not None:
            self.dry_raw = int(dry_raw)
        if wet_raw is not None:
            self.wet_raw = int(wet_raw)
        # Ré-ordonner si inversé
        if self.dry_raw <= self.wet_raw:
            self.dry_raw, self.wet_raw = self.wet_raw, self.dry_raw
