# main.py — Wi-Fi, MQTT, relais, humidité du sol + DHT11 sur GP15
import time
import machine

import secrets
from wifi import ensure_wifi
from mqtt_client import MQTTClient
import relay
from hw080 import HW080Soil
import ujson as json

from dht11_sensor import DHT11Sensor   # <-- AJOUT

LED = machine.Pin("LED", machine.Pin.OUT)

# Capteurs
soil = HW080Soil(adc_pin=26, dry_raw=58000, wet_raw=30000)
dht = DHT11Sensor(pin=15, label="zbeubarium-dht11")  # <-- DHT11 sur GP15

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

        # Etat initial (retained)
        client.publish(secrets.MQTT_STATE_TOPIC, relay.state_json(), retain=True)

        # Boucle principale
        last_pub = time.ticks_ms()
        period_ms = 10_000  # 10 s

        while True:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_pub) > period_ms:
                # Publication Hello
                client.publish(secrets.MQTT_TOPIC, "Hello World", retain=False)

                # Sol
                soil_data = soil.measure()
                client.publish(secrets.MQTT_STATE_TOPIC + "/soil", json.dumps(soil_data))
                print("Soil ->", soil_data)

                # DHT11 (T/H)
                dht_data = dht.read()
                client.publish(secrets.MQTT_STATE_TOPIC + "/dht11", json.dumps(dht_data))
                print("DHT11 ->", dht_data)

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
