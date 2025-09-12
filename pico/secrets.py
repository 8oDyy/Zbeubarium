WIFI_SSID = "CIEL1_2.4G"
WIFI_PASSWORD = "StMichel2023-25"

MQTT_HOST = "20.251.152.188"   # IP/hostname de ton broker
MQTT_PORT = 1883
MQTT_USER = "picoUser"            # ex: "user" ou None
MQTT_PASSWORD = "samy"         # ex: "pass" ou None
MQTT_CLIENT_ID = "pico2w-001"

# Topics
MQTT_TOPIC = "pico2w/test"           # (tu l'utilises déjà)
MQTT_LWT_TOPIC = "pico2w/status"
MQTT_CMD_TOPIC = "pico2w/relay/cmd"  # <— on s’abonne ici pour recevoir les commandes
MQTT_STATE_TOPIC = "pico2w/relay/state"  # <— on publie l’état ici