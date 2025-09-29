# dht11_sensor.py
# Module simple et robuste pour lire un capteur DHT11 en MicroPython (Raspberry Pi Pico / Pico W)
#
# - Lecture avec retries et rejet de la 1ʳᵉ mesure (souvent instable)
# - Rate-limit intégré pour éviter d'interroger trop vite le capteur
# - Méthode utilitaire publish() pour publier en MQTT au format JSON

import time
import machine
import ujson as json

try:
    import dht  # module MicroPython standard
except ImportError as e:
    raise ImportError("Le module 'dht' est manquant dans ton firmware MicroPython.") from e


class DHT11Sensor:
    """
    DHT11 branché sur une broche GPIO du Pico.
    Paramètres:
        pin (int): numéro de GPIO (ex: 15 pour GP15)
        warmup_reads (int): nombre de lectures à jeter au démarrage
        max_retries (int): nombre d’essais par lecture
        min_interval_s (float): délai mini entre deux lectures pour fiabilité
        label (str): nom du capteur (utilisé dans le JSON publié)
    """
    def __init__(self, pin: int = 15, *, warmup_reads: int = 1,
                 max_retries: int = 3, min_interval_s: float = 2.0,
                 label: str = "dht11"):
        self.pin = machine.Pin(pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self._sensor = dht.DHT11(self.pin)
        self._warmup_remaining = max(0, warmup_reads)
        self._max_retries = max_retries
        self._min_interval_ms = int(min_interval_s * 1000)
        self._last_ms = -10_000_000
        self.label = label

    def _do_measure(self):
        # Appelle .measure() avec retries (le DHT11 peut échouer sporadiquement)
        last_err = None
        for _ in range(self._max_retries):
            try:
                self._sensor.measure()
                return True
            except Exception as e:
                last_err = e
                time.sleep_ms(250)
        raise last_err if last_err else RuntimeError("Mesure DHT11 inconnue")

    def read(self) -> dict:
        """
        Retourne un dict: {
            "ok": bool, "t": float|None, "h": float|None,
            "ts": int (epoch sec), "ms": int (ticks_ms),
            "sensor": str
        }
        """
        # Respecte l’intervalle mini
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_ms) < self._min_interval_ms:
            # Re-donne la main un court instant si on insiste trop vite
            time.sleep_ms(self._min_interval_ms - time.ticks_diff(now, self._last_ms))

        # Mesure
        self._do_measure()
        self._last_ms = time.ticks_ms()

        # Première(s) mesure(s) jetées (instables sur DHT11)
        if self._warmup_remaining > 0:
            self._warmup_remaining -= 1
            # Attendre un peu avant de refaire une vraie lecture
            time.sleep_ms(500)
            self._do_measure()

        try:
            t = self._sensor.temperature()   # °C (int sur DHT11)
            h = self._sensor.humidity()      # %  (int sur DHT11)
            ok = (t is not None) and (h is not None)
        except Exception as e:
            return {
                "ok": False, "t": None, "h": None,
                "ts": self._epoch_s(), "ms": time.ticks_ms(),
                "sensor": self.label, "err": repr(e),
            }

        return {
            "ok": ok,
            "t": float(t) if t is not None else None,
            "h": float(h) if h is not None else None,
            "ts": self._epoch_s(),
            "ms": time.ticks_ms(),
            "sensor": self.label,
        }

    def publish(self, mqtt_client, topic: str) -> bool:
        """
        Lit le capteur et publie en MQTT (payload JSON).
        Renvoie True si publié, False sinon.
        """
        data = self.read()
        try:
            payload = json.dumps(data)
            mqtt_client.publish(topic, payload)
            return True
        except Exception:
            return False

    @staticmethod
    def _epoch_s():
        # Sur Pico, time.time() renvoie depuis 2000 selon firmware;
        # ce n’est pas critique pour le logging, on renvoie "time.time()" tel quel.
        try:
            return int(time.time())
        except Exception:
            return 0
