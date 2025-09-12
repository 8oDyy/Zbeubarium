# wifi.py
import network
import time

def connect_wifi(ssid, password, timeout_s=30):
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)

    if not wlan.isconnected():
        wlan.connect(ssid, password)
        t0 = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
                return False
            time.sleep(0.2)
    return True

def ensure_wifi(ssid, password, retries=3, delay_s=3):
    for i in range(retries):
        if connect_wifi(ssid, password):
            print("Wi-Fi connecté:", network.WLAN(network.STA_IF).ifconfig())
            return True
        print("Échec Wi-Fi, retry", i + 1, "/", retries)
        time.sleep(delay_s)
    print("Impossible de se connecter au Wi-Fi — vérifie SSID/mot de passe.")
    return False
