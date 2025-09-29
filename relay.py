"""
relay.py  –  Gestion d’un module 2 relais pour Raspberry Pi Pico
Par défaut : IN1 = GP16, IN2 = GP17, entrées actives à l’état bas.
"""

from machine import Pin

# --- configuration interne ---
_ACTIVE_LOW = True
_R1 = None
_R2 = None

def init(pin1: int = 16, pin2: int = 17, active_low: bool = True):
    """
    Initialise les deux relais. À appeler une seule fois au démarrage.

    """
    global _R1, _R2, _ACTIVE_LOW
    _ACTIVE_LOW = active_low
    _R1 = Pin(pin1, Pin.OUT, value=_off_value())
    _R2 = Pin(pin2, Pin.OUT, value=_off_value())

def _on_value():  return 0 if _ACTIVE_LOW else 1
def _off_value(): return 1 if _ACTIVE_LOW else 0
def _check_init():
    if _R1 is None or _R2 is None:
        raise RuntimeError("relay.init() doit être appelé avant utilisation")

# --- Commandes simples ---
def lampe_on():   _check_init(); _R1.value(_on_value())
def lampe_off():  _check_init(); _R1.value(_off_value())
def pompe_on():   _check_init(); _R2.value(_on_value())
def pompe_off():  _check_init(); _R2.value(_off_value())
def both_on():   lampe_on(); pompe_on()
def both_off():  lampe_off(); pompe_off()

# --- État actuel ---
def state_dict() -> dict:
    """
    Retourne l’état actuel sous forme de dictionnaire : {"r1": "ON"/"OFF", "r2": ...}
    """
    _check_init()
    def s(pin):
        v = pin.value()
        return "ON" if ((v == 0) if _ACTIVE_LOW else (v == 1)) else "OFF"
    return {"r1": s(_R1), "r2": s(_R2)}

def state_json() -> str:
    """
    Retourne l’état actuel au format JSON minimal.
    """
    st = state_dict()
    return f'{{"r1":"{st["r1"]}","r2":"{st["r2"]}"}}'

# --- Interpréteur de commande texte ---
def handle_cmd(cmd: str) -> bool:
    """
    Exécute une commande texte :
      on1 / off1 / on2 / off2 / on / off / status
    Renvoie True si la commande est reconnue (même pour 'status'), sinon False.
    """
    _check_init()
    c = (cmd or "").strip().lower()
    if   c == "on1":  lampe_on()
    elif c == "off1": lampe_off()
    elif c == "on2":  pompe_on()
    elif c == "off2": pompe_off()
    elif c == "on":   both_on()
    elif c == "off":  both_off()
    elif c == "status":
        pass
    else:
        return False
    return True
