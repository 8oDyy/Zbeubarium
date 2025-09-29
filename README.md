 # Zbeubarium – Raspberry Pi Pico W + MQTT

Relais • Humidité du sol (HW-080) • Temp/Hum (DHT11) • Luminosité (KY-018 LDR)

> MicroPython firmware for a Pico W that controls **relays** and publishes **sensor telemetry** to **MQTT** with graceful error reporting (DHT11 unplugged detection).

---

## Table of Contents

* [Overview](#overview)
* [Hardware](#hardware)
* [Wiring](#wiring)
* [MQTT Topics & Payloads](#mqtt-topics--payloads)
* [Project Layout](#project-layout)
* [Configuration (`secrets.py`)](#configuration-secretspy)
* [Deploy & Run](#deploy--run)
* [Troubleshooting](#troubleshooting)
* [License](#license)

---

## Overview

* **Board**: Raspberry Pi **Pico W** (MicroPython)
* **I/O**:

  * 2× **Relays** (active-low) on **GP16/GP17**
  * **Soil moisture** (**HW-080**) on **ADC0 / GP26**
  * **DHT11** temperature & humidity on **GP15**
    ↳ publishes a **JSON error** if unplugged/failed
  * **KY-018 (LDR)** luminosity on **ADC1 / GP27**
* **MQTT**: LWT (online/offline), heartbeat, retained state, command topic for relays

---

## Hardware

* Raspberry Pi **Pico W** (Wi-Fi)
* **2-Relay module** (active-low inputs; many require 5 V power)
* **HW-080** (probe + HW-103 analog board)
* **DHT11** (module recommended; includes pull-up)
* **KY-018 LDR** (module with analog output preferred)

> ⚠️ Pico W GPIOs are **3.3 V only** on analog inputs (ADC). Ensure sensor AO never exceeds 3.3 V.

---

## Wiring

### GPIO Map (Pico W)

| Function      | Module  |        Pico Pin | Notes                          |
| ------------- | ------- | --------------: | ------------------------------ |
| Relay 1 IN1   | 2-Relay |        **GP16** | `active_low=True`              |
| Relay 2 IN2   | 2-Relay |        **GP17** | `active_low=True`              |
| Soil AO       | HW-080  | **GP26 / ADC0** | `adc_pin=26`                   |
| DHT11 DATA    | DHT11   |        **GP15** | `pin=15`                       |
| LDR AO        | KY-018  | **GP27 / ADC1** | `adc_pin=27`, `high_side=True` |
| VCC (sensors) | all     |         **3V3** | prefer 3.3 V                   |
| GND           | all     |         **GND** | common ground                  |

**Relays power**

* Many relay boards **need 5 V** on *VCC* to actuate properly.
* Inputs are logic-level tolerant; still keep Pico signals at **3.3 V**.

**HW-080**

* If you power the module with 5 V, confirm the **AO line ≤ 3.3 V** before connecting to Pico ADC.

**KY-018**

* With bare LDR, make a **divider** (LDR + fixed resistor) to get 0–3.3 V.
* With a KY-018 module, power at 3.3 V and read **AO** on GP27.

---

## MQTT Topics & Payloads

Base topics come from **`secrets.py`**:

```py
MQTT_TOPIC          # heartbeat
MQTT_STATE_TOPIC    # states & measurements
MQTT_CMD_TOPIC      # relay commands
MQTT_LWT_TOPIC      # online/offline (LWT)
```

### Presence (LWT)

* On connect: `MQTT_LWT_TOPIC` → `"online"`
* On disconnect: broker publishes LWT → `"offline"`

### Heartbeat

* **Topic**: `MQTT_TOPIC`
* **Payload**: `"Hello World"` (every 10 s)

### Relay State (retained)

* **Topic**: `MQTT_STATE_TOPIC`
* **Payload** (example):

```json
{"rel1": true, "rel2": false, "ts": 1609463300}
```

### Relay Commands (plain text on `MQTT_CMD_TOPIC`)

| Message        | Action                                        |
| -------------- | --------------------------------------------- |
| `on1` / `off1` | Relay 1 ON/OFF                                |
| `on2` / `off2` | Relay 2 ON/OFF                                |
| `on` / `off`   | Both relays ON/OFF                            |
| `status`       | Republishes relay state on `MQTT_STATE_TOPIC` |

### Soil Moisture (HW-080)

* **Topic**: `MQTT_STATE_TOPIC/soil`
* **Payload** (example):

```json
{
  "sensor": "hw080",
  "ok": true,
  "raw": 14040,
  "percent": 100.0,
  "voltage": 0.707,
  "ts": 1609463394
}
```

### DHT11 (OK)

* **Topic**: `MQTT_STATE_TOPIC/dht11`
* **Payload** (example; depends on your `DHT11Sensor.read()`):

```json
{
  "sensor": "zbeubarium-dht11",
  "ok": true,
  "temp": 23.0,
  "hum": 51.0,
  "ts": 1609463400
}
```

### DHT11 (unplugged / error)

* **Topic**: `MQTT_STATE_TOPIC/dht11`
* **Payload**:

```json
{
  "sensor": "zbeubarium-dht11",
  "ok": false,
  "error": "unplugged or not detected",
  "ts": 1609463400
}
```

> The “unplugged” JSON is **re-published periodically** while the sensor is missing or failing.

### Luminosity (KY-018 LDR)

* **Topic**: `MQTT_STATE_TOPIC/light`
* **Payload** (example):

```json
{
  "sensor": "zbeubarium-ldr",
  "ok": true,
  "raw": 3337,
  "voltage": 2.689,
  "lux": 1.20,
  "resistance": 44382.5,
  "ms": 582091,
  "ts": 1609463420
}
```

* On read error:

```json
{"sensor":"zbeubarium-ldr","ok":false,"error":"<message>","ts":1609463425}
```

---

## Project Layout

```
/ (Pico)
  main.py
  relay.py
  wifi.py
  mqtt_client.py
  hw080.py
  ky018_ldr.py
  dht11_sensor.py
  secrets.py
```

---

## Configuration (`secrets.py`)

```python
WIFI_SSID = "YourSSID"
WIFI_PASSWORD = "YourPass"

MQTT_HOST = "192.168.0.10"     # or public IP/DNS
MQTT_PORT = 1883
MQTT_USER = "user"
MQTT_PASSWORD = "pass"

MQTT_CLIENT_ID = "pico-zbeubarium-01"
MQTT_TOPIC = "zbeubarium/hello"
MQTT_STATE_TOPIC = "zbeubarium/state"
MQTT_CMD_TOPIC = "zbeubarium/cmd"
MQTT_LWT_TOPIC = "zbeubarium/status"
```

---

## Deploy & Run

**Run directly (dev):**

```bash
mpremote run main.py
```

**Copy files to the Pico (run at boot):**

```bash
mpremote fs cp main.py :main.py
mpremote fs cp secrets.py :secrets.py
mpremote fs cp relay.py :relay.py
mpremote fs cp wifi.py :wifi.py
mpremote fs cp mqtt_client.py :mqtt_client.py
mpremote fs cp hw080.py :hw080.py
mpremote fs cp ky018_ldr.py :ky018_ldr.py
mpremote fs cp dht11_sensor.py :dht11_sensor.py
```

---

## Troubleshooting

* **MQTT timeouts**: verify broker IP/port 1883 (UFW/NSG), credentials, ACL, `ssl_enabled=False`.
* **Relays do not actuate**: power relay board at **5 V**; inputs are **active-low** (handled in code).
* **DHT11 missing**: check GP15 + 3V3 + GND; modules usually include pull-up.
* **LDR readings weird**: ensure AO ≤ 3.3 V; if bare LDR, use divider with proper resistor value.

---

## License

Personal/educational project — adapt freely.
