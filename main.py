# main.py — Wi-Fi, MQTT, relais, sol (HW080) + DHT11 (GP15, unplugged-safe) + LDR KY-018 (ADC GP27)
import time
import machine
import ujson as json

import secrets
from wifi import ensure_wifi
from mqtt_client import MQTTClient
import relay
from hw080 import HW080Soil

LED = machine.Pin("LED", machine.Pin.OUT)

# --- Helpers ---
def now_ts():
    try:
        return int(time.time())
    except Exception:
        return int(time.ticks_ms())

def publish_unplugged(client, topic, label, error="unplugged or not detected", retain=True):
    payload = json.dumps({
        "sensor": label,
        "ok": False,
        "error": error,
        "ts": now_ts()
    })
    try:
        client.publish(topic, payload, retain=retain)
    except Exception as e:
        print("publish_unplugged error:", e)

def blink(n=2, delay=0.1):
    for _ in range(n):
        LED.on(); time.sleep(delay)
        LED.off(); time.sleep(delay)

def make_on_msg(client):
    """Callback MQTT : reçoit une commande texte et pilote les relais via relay.py."""
    def on_msg(topic, payload):
        try:
            t = topic.decode() if isinstance(topic, (bytes, bytearray)) else str(topic)
            if t != secrets.MQTT_CMD_TOPIC:
                return
            p = payload.decode().strip() if isinstance(payload, (bytes, bytearray)) else str(payload).strip()

            if relay.handle_cmd(p):  # on1/off1/on2/off2/on/off/status
                client.publish(secrets.MQTT_STATE_TOPIC, relay.state_json(), retain=True)
                blink(1, 0.03)
        except Exception as e:
            print("Erreur on_msg:", e)
    return on_msg

# --- Capteurs ---
soil = HW080Soil(adc_pin=26, dry_raw=58000, wet_raw=30000)

# DHT11 (tolérant aux erreurs d'import/instanciation)
dht = None
_dht_import_error = None
try:
    from dht11_sensor import DHT11Sensor
    dht = DHT11Sensor(pin=15, label="zbeubarium-dht11")  # GP15
except Exception as e:
    _dht_import_error = str(e)

# KY-018 (LDR) sur ADC GP27
ldr = None
try:
    from ky018_ldr import KY018LDR
    ldr = KY018LDR(adc_pin=27, label="zbeubarium-ldr", high_side=True)
except Exception as e:
    # On ne stoppe pas le programme si le module n'existe pas
    print("KY018 import error:", e)
    ldr = None

def main():
    # 0) Initialisation des relais
    relay.init(pin1=16, pin2=17, active_low=True)

    # 1) Wi-Fi
    ok = ensure_wifi(secrets.WIFI_SSID, secrets.WIFI_PASSWORD, retries=5, delay_s=2)
    if not ok:
        for _ in range(10):
            LED.toggle(); time.sleep(0.1)
        return

    # 2) MQTT (LWT)
    client = MQTTClient(
        client_id=secrets.MQTT_CLIENT_ID,
        server=secrets.MQTT_HOST,
        port=secrets.MQTT_PORT,
        user=secrets.MQTT_USER,
        password=secrets.MQTT_PASSWORD,
        keepalive=60,
        ssl_enabled=False,
        lwt_topic=secrets.MQTT_LWT_TOPIC,
        lwt_msg=b"offline",
        lwt_retain=True,
    )

    try:
        client.connect(clean_session=True)
        print("MQTT connecté")
        client.publish(secrets.MQTT_LWT_TOPIC, b"online", retain=True)

        # Abonnement & callback
        client.set_callback(make_on_msg(client))
        client.subscribe(secrets.MQTT_CMD_TOPIC)

        # Etat initial (retained) — état relais
        client.publish(secrets.MQTT_STATE_TOPIC, relay.state_json(), retain=True)

        # Topics
        dht_topic = secrets.MQTT_STATE_TOPIC + "/dht11"
        ldr_topic = secrets.MQTT_STATE_TOPIC + "/light"
        soil_topic = secrets.MQTT_STATE_TOPIC + "/soil"

        # DHT11 : annonce d'état initial
        dht_connected = False
        if dht is None:
            publish_unplugged(client, dht_topic, label="zbeubarium-dht11",
                              error=_dht_import_error or "module not found")
        else:
            try:
                first = dht.read()
                if isinstance(first, dict) and first.get("ok", True) is True:
                    dht_connected = True
                    client.publish(dht_topic, json.dumps(first), retain=True)
                    print("DHT11 ->", first)
                else:
                    publish_unplugged(client, dht_topic, label=getattr(dht, "label", "zbeubarium-dht11"),
                                      error="bad reading")
            except Exception as e:
                publish_unplugged(client, dht_topic, label=getattr(dht, "label", "zbeubarium-dht11"),
                                  error=str(e))

        # LDR : pas d'état “unplugged” forcé ici (certains montages renvoient 0 légitime).
        # Si tu veux, on peut publier un JSON d'erreur si lecture impossible.

        # Boucle principale
        last_pub = time.ticks_ms()
        period_ms = 10_000  # 10 s

        while True:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_pub) > period_ms:
                # Heartbeat
                client.publish(secrets.MQTT_TOPIC, "Hello World", retain=False)

                # Sol
                try:
                    soil_data = soil.measure()
                    client.publish(soil_topic, json.dumps(soil_data))
                    print("Soil ->", soil_data)
                except Exception as e:
                    print("Soil error:", e)

                # DHT11 (T/H) — mesure si connecté, sinon republie l’état unplugged
                if dht and dht_connected:
                    try:
                        dht_data = dht.read()
                        client.publish(dht_topic, json.dumps(dht_data), retain=True)
                        print("DHT11 ->", dht_data)
                    except Exception as e:
                        dht_connected = False
                        publish_unplugged(client, dht_topic, label=getattr(dht, "label", "zbeubarium-dht11"),
                                          error=str(e))
                else:
                    publish_unplugged(client, dht_topic, label="zbeubarium-dht11",
                                      error="unplugged or not detected")

                # LDR (luminosité)
                if ldr:
                    try:
                        ldr_data = ldr.read()
                        client.publish(ldr_topic, json.dumps(ldr_data))
                        print("LDR ->", ldr_data)
                    except Exception as e:
                        # Si tu préfères publier une erreur sur /light :
                        err = json.dumps({"sensor": "zbeubarium-ldr", "ok": False, "error": str(e), "ts": now_ts()})
                        client.publish(ldr_topic, err)
                        print("LDR error:", e)

                last_pub = now
                blink(1, 0.05)

            client.loop()       # keepalive (PING)
            client.check_msg()  # commandes entrantes
            time.sleep(0.05)

    except (OSError, RuntimeError) as e:
        print("Erreur MQTT:", e)
    finally:
        try:
            client.publish(secrets.MQTT_LWT_TOPIC, b"offline", retain=True)
        except OSError:
            pass
        try:
            client.disconnect()
        except OSError:
            pass

if __name__ == "__main__":
    main()