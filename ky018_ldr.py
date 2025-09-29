# ky018_ldr.py
# LDR (KY-018 / GL5528) -> lux pour Raspberry Pi Pico (MicroPython)
# - Pont diviseur avec R_fixed (par défaut 10k)
# - Gestion orientation: high_side=False (R_fixed en haut) / True (LDR en haut)
# - Conversion lux via modèle puissance: R ≈ A * lux^(-gamma)  => lux ≈ (A/R)^(1/gamma)
# - Defaults GL5528 crédibles: A≈60000, gamma=0.7 (10 lux ~ 8–20kΩ)
#
# Champs renvoyés: raw (0..4095), voltage (V), resistance (Ω), lux (estimation),
#                  ts, ms, sensor, model, ok

import time
import machine
import math
import ujson as json

def _median(vals):
    s = sorted(vals)
    n = len(s)
    return s[n//2] if n % 2 == 1 else 0.5 * (s[n//2 - 1] + s[n//2])

class KY018LDR:
    def __init__(self,
                 adc_pin: int = 27,          # GP27 = ADC1
                 r_fixed_ohms: float = 10_000.0,  # résistance série (ohm)
                 vref: float = 3.3,
                 samples: int = 9,           # nb d'échantillons pour médiane
                 sample_delay_ms: int = 2,
                 label: str = "ky018",
                 # Modèle GL5528: R ≈ A * lux^-gamma
                 A: float = 60_000.0,        # dérivé de ~12kΩ @10lux => 12k*10^0.7 ≈ 60k
                 gamma: float = 0.7,         # pente typique GL5528
                 high_side: bool = False):   # False: Vref->Rfixed->node->LDR->GND ; True: Vref->LDR->node->Rfixed->GND
        self._adc = machine.ADC(adc_pin)
        self.r_fixed = float(r_fixed_ohms)
        self.vref = float(vref)
        self.samples = max(1, int(samples))
        self.sample_delay_ms = max(0, int(sample_delay_ms))
        self.label = label
        self.A = float(A)
        self.gamma = float(gamma)
        self.high_side = bool(high_side)

    # --------- calib helpers ---------
    def recalibrate(self, lux_at_point: float, r_at_point_ohms: float):
        """Fixe A à partir d'un point (lux, R). gamma reste inchangée."""
        if lux_at_point <= 0 or r_at_point_ohms <= 0:
            return
        # R = A * lux^-gamma => A = R * lux^gamma
        self.A = float(r_at_point_ohms) * (lux_at_point ** self.gamma)

    def calibrate_two_points(self, lux1: float, r1: float, lux2: float, r2: float):
        """Calibre (A, gamma) à partir de deux points (lux, R) distincts."""
        if lux1 <= 0 or lux2 <= 0 or r1 <= 0 or r2 <= 0 or lux1 == lux2:
            return
        # ln R = ln A - gamma * ln lux  => régression exacte à 2 points
        lnR1, lnR2 = math.log(r1), math.log(r2)
        lnL1, lnL2 = math.log(lux1), math.log(lux2)
        gamma = (lnR1 - lnR2) / (lnL2 - lnL1)  # attention à l'ordre
        lnA = lnR1 + gamma * lnL1
        self.gamma = float(gamma)
        self.A = float(math.exp(lnA))

    # --------- lecture bas niveau ---------
    def _read_raw12(self) -> int:
        # ADC 16 bits sur Pico -> on ramène sur 12 bits (0..4095)
        buf = []
        for _ in range(self.samples):
            v = self._adc.read_u16()
            buf.append(v >> 4)
            if self.sample_delay_ms:
                time.sleep_ms(self.sample_delay_ms)
        return int(_median(buf))

    def _raw_to_voltage(self, raw12: int) -> float:
        return (raw12 / 4095.0) * self.vref

    def _voltage_to_rldr(self, v_out: float) -> float:
        # Pont:
        # - high_side=False (défaut):  Vref -> R_fixed -> node -> LDR -> GND
        #       Vout = Vref * R_LDR / (R_fixed + R_LDR)  => R_LDR = R_fixed * Vout / (Vref - Vout)
        # - high_side=True:           Vref -> LDR -> node -> R_fixed -> GND
        #       Vout = Vref * R_fixed / (R_fixed + R_LDR) => R_LDR = R_fixed * (Vref / Vout - 1)
        if v_out <= 0.0 or v_out >= self.vref:
            return float("inf")
        if self.high_side:
            return self.r_fixed * (self.vref / v_out - 1.0)
        else:
            return self.r_fixed * (v_out / (self.vref - v_out))

    def _resistance_to_lux(self, r_ldr: float) -> float:
        # lux = (A / R)^(1/gamma)
        if not math.isfinite(r_ldr) or r_ldr <= 0.0:
            return 0.0
        return (self.A / r_ldr) ** (1.0 / self.gamma)

    # --------- API ---------
    def read(self) -> dict:
        raw = self._read_raw12()
        v = self._raw_to_voltage(raw)
        r = self._voltage_to_rldr(v)
        lux = self._resistance_to_lux(r)
        ok = math.isfinite(lux)
        return {
            "ok": bool(ok),
            "raw": int(raw),
            "voltage": float(v),
            "resistance": float(r),
            "lux": float(lux),
            "ts": int(time.time()),
            "ms": time.ticks_ms(),
            "sensor": self.label,
            "model": "LDR(GL5528)-A{}-g{}".format(int(self.A), self.gamma)
        }

    def publish(self, mqtt_client, topic: str) -> bool:
        try:
            mqtt_client.publish(topic, json.dumps(self.read()))
            return True
        except Exception:
            return False
