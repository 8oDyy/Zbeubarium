# hw080.py — Capteur d'humidité de sol HW-080 (sortie analogique)
# MicroPython (Raspberry Pi Pico / Pico W)
#
# Fournit une petite classe pour lire l'ADC, moyenner, et convertir en %.
# Aucune dépendance réseau/MQTT ici : ton main.py s'en charge.

import time
import machine

class HW080Soil:
    """
    Lecture capteur HW080 (résistif) via ADC.
    - adc_pin   : GP26=ADC0, GP27=ADC1, GP28=ADC2 (par défaut GP26)
    - power_pin : (optionnel) GPIO qui alimente la sonde via un MOSFET/Transistor.
                  Si fourni, la sonde n'est alimentée que pendant la mesure.
    - dry_raw / wet_raw : valeurs brutes mesurées à sec / très humide (calibration).
                          Par défaut des valeurs typiques à ajuster chez toi.
    """

    def __init__(self, adc_pin=26, power_pin=None, dry_raw=58000, wet_raw=30000):
        self.adc = machine.ADC(adc_pin)
        self.power = None
        if power_pin is not None:
            self.power = machine.Pin(power_pin, machine.Pin.OUT, value=0)  # 0 = OFF
        self.dry_raw = int(dry_raw)
        self.wet_raw = int(wet_raw)

    # ----- gestion alim optionnelle -----
    def _power_on(self):
        if self.power:
            self.power.value(1)

    def _power_off(self):
        if self.power:
            self.power.value(0)

    # ----- mesures -----
    def read_raw(self, samples=16, sample_delay_ms=2, warmup_ms=50):
        """
        Retourne la moyenne de 'samples' lectures ADC (0..65535).
        Si power_pin est défini, alimente la sonde uniquement pendant la mesure.
        """
        self._power_on()
        if warmup_ms:
            time.sleep_ms(int(warmup_ms))

        total = 0
        n = max(1, int(samples))
        for _ in range(n):
            total += self.adc.read_u16()
            if sample_delay_ms:
                time.sleep_ms(int(sample_delay_ms))

        self._power_off()
        return total // n

    def to_percent(self, raw):
        """
        Convertit une valeur brute en pourcentage 0..100 borné.
        NOTE: HW-080 => plus c'est humide, plus la valeur brute est BASSE.
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
        """Effectue une mesure et renvoie uniquement le pourcentage (float)."""
        raw = self.read_raw(**kwargs)
        return self.to_percent(raw)

    def measure(self, **kwargs):
        """
        Retourne un dict prêt à publier/logguer :
        { "percent": 63.4, "raw": 35120, "ts": 1699999999 }
        """
        raw = self.read_raw(**kwargs)
        return {
            "percent": round(self.to_percent(raw), 1),
            "raw": raw,
            "ts": time.time()
        }