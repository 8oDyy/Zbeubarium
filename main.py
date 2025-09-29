# main.py — Wi-Fi, MQTT, commandes relais + Thermistor KY-013 (ADC GP27)

import time
import machine
import ujson as json

import secrets
from wifi import ensure_wifi
from mqtt_client import MQTTClient
import relay
from ky018_ldr import KY018LDR

LED = machine.Pin("LED", machine.Pin.OUT)
ldr = KY018LDR(adc_pin=27, label="zbeubarium-ldr", high_side=True)

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
                # PUB: état relais sur topic dédié
                client.publish(secrets.MQTT_STATE_TOPIC, relay.state_json(), retain=True)
                blink(1, 0.03)
        except Exception as e:
            print("Erreur on_msg:", e)
    return on_msg

def main():
    # 0) Initialisation des relais (adapte les pins/active_low si besoin)
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

        # Boucle principale
        last_pub = time.ticks_ms()
        period_ms = 10_000  # 10 s

        while True:
            now = time.ticks_ms()
            if time.ticks_diff(now, last_pub) > period_ms:
                # Heartbeat
                client.publish(secrets.MQTT_TOPIC, "Hello World", retain=False)

                # Capteur thermistor (KY-013)
                ldr_data = ldr.read()
                client.publish(secrets.MQTT_STATE_TOPIC + "/light", json.dumps(ldr_data))
                print("LDR ->", ldr_data)

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
