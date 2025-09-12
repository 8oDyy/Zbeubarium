# mqtt_client.py — client MQTT v3.1.1 minimal (QoS 0) pour MicroPython
import usocket as socket
import ustruct as struct
import time
try:
    import ussl as ssl
except Exception:
    ssl = None


def _to_bytes(s):
    if isinstance(s, (bytes, bytearray)):
        return bytes(s)
    if isinstance(s, str):
        return s.encode()
    return str(s).encode()


class MQTTClient:
    def __init__(self, client_id, server, port=1883, user=None, password=None,
                 keepalive=60, ssl_enabled=False, ssl_params=None,
                 lwt_topic=None, lwt_msg=b"offline", lwt_retain=True):
        self.client_id = _to_bytes(client_id)
        self.server = server
        self.port = port
        self.user = None if user is None else _to_bytes(user)
        self.password = None if password is None else _to_bytes(password)
        self.keepalive = keepalive
        self.ssl_enabled = ssl_enabled
        self.ssl_params = ssl_params or {}
        self.sock = None
        self._cb = None  # callback(topic_bytes, payload_bytes)
        self.lwt_topic = None if lwt_topic is None else _to_bytes(lwt_topic)
        self.lwt_msg = _to_bytes(lwt_msg)
        self.lwt_retain = lwt_retain
        self.last_ping = time.ticks_ms()

    # ---------- utils encodage ----------
    @staticmethod
    def _encode_varlen(x: int) -> bytes:
        out = b""
        while True:
            digit = x % 128
            x //= 128
            if x > 0:
                digit |= 0x80
            out += bytes([digit])
            if x == 0:
                break
        return out

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.read(n - len(buf))
            if not chunk:
                raise OSError("socket closed")
            buf += chunk
        return buf

    # ---------- transport ----------
    def _write(self, data):
        self.sock.write(data)

    # ---------- API ----------
    def set_callback(self, f):
        self._cb = f

    def connect(self, clean_session=True):
        try:
            addr = socket.getaddrinfo(self.server, self.port)[0][-1]
            s = socket.socket()
            s.connect(addr)
            if self.ssl_enabled and ssl:
                s = ssl.wrap_socket(s, **self.ssl_params)
            self.sock = s

            # CONNECT
            proto_name = b"MQTT"
            proto_level = 4  # 3.1.1
            flags = 0
            if clean_session:
                flags |= 0x02
            if self.user is not None:
                flags |= 0x80
                if self.password is not None:
                    flags |= 0x40
            if self.lwt_topic is not None:
                flags |= 0x04
                if self.lwt_retain:
                    flags |= 0x20

            vh = struct.pack("!H", len(proto_name)) + proto_name
            vh += bytes([proto_level, flags])
            vh += struct.pack("!H", self.keepalive)

            payload = struct.pack("!H", len(self.client_id)) + self.client_id
            if self.lwt_topic is not None:
                payload += struct.pack("!H", len(self.lwt_topic)) + self.lwt_topic
                payload += struct.pack("!H", len(self.lwt_msg)) + self.lwt_msg
            if self.user is not None:
                payload += struct.pack("!H", len(self.user)) + self.user
                if self.password is not None:
                    payload += struct.pack("!H", len(self.password)) + self.password

            pkt = b"\x10" + self._encode_varlen(len(vh) + len(payload)) + vh + payload
            self._write(pkt)

            # CONNACK attendu: 0x20 0x02 0x00 0x00
            resp = self._recv_exact(4)
            if resp[0] != 0x20 or resp[1] != 0x02 or resp[3] != 0x00:
                raise OSError("MQTT CONNACK invalide: %s" % (resp,))
            self.last_ping = time.ticks_ms()
        except OSError as e:
            try:
                if self.sock:
                    self.sock.close()
            except OSError:
                pass
            self.sock = None
            raise OSError("Échec connexion MQTT: %r" % (e,))

    def publish(self, topic, msg=b"", retain=False):
        t = _to_bytes(topic)
        m = _to_bytes(msg)
        hdr = 0x30  # PUBLISH QoS0 DUP=0
        if retain:
            hdr |= 0x01
        vh = struct.pack("!H", len(t)) + t
        rl = len(vh) + len(m)
        self._write(bytes([hdr]) + self._encode_varlen(rl) + vh + m)

    def subscribe(self, topic):
        t = _to_bytes(topic)
        # SUBSCRIBE (QoS 1 requis par le protocole pour la frame SUBSCRIBE)
        pkt = b"\x82"  # packet type + flags
        packet_id = b"\x00\x01"  # ID fixe simple
        payload = struct.pack("!H", len(t)) + t + b"\x00"  # QoS0
        rl = len(packet_id) + len(payload)
        self._write(pkt + self._encode_varlen(rl) + packet_id + payload)
        # Consommer SUBACK (tolérant si absent/partial selon port)
        try:
            self.sock.settimeout(2)
            _ = self._recv_exact(5)  # 0x90 len=3 id ret
        except Exception:
            pass
        finally:
            try:
                self.sock.settimeout(5)
            except Exception:
                pass

    def check_msg(self):
        """Lecture non bloquante d'un éventuel PUBLISH, appelle le callback si défini."""
        if not self.sock:
            return
        try:
            self.sock.settimeout(0)
            first = self.sock.read(1)
            if not first:
                return
            hdr = first[0]
            msg_type = hdr >> 4

            # decode remaining length
            rem_len = 0
            mult = 1
            while True:
                b = self.sock.read(1)
                if not b:
                    return
                digit = b[0]
                rem_len += (digit & 0x7F) * mult
                if (digit & 0x80) == 0:
                    break
                mult *= 128

            if msg_type == 3:  # PUBLISH QoS0
                tlen = struct.unpack("!H", self._recv_exact(2))[0]
                topic = self._recv_exact(tlen)
                payload_len = rem_len - 2 - tlen  # QoS0 => pas de packet id
                payload = self._recv_exact(payload_len) if payload_len > 0 else b""
                if self._cb:
                    self._cb(topic, payload)
            else:
                # consomme le reste pour garder la socket propre
                if rem_len:
                    _ = self._recv_exact(rem_len)
        except OSError:
            return
        finally:
            try:
                self.sock.settimeout(5)
            except Exception:
                pass

    def ping(self):
        if not self.sock:
            return
        self._write(b"\xC0\x00")
        self.last_ping = time.ticks_ms()

    def loop(self):
        # à appeler régulièrement; envoie un PINGREQ avant keepalive
        if time.ticks_diff(time.ticks_ms(), self.last_ping) > (self.keepalive - 5) * 1000:
            self.ping()

    def disconnect(self):
        try:
            if self.sock:
                self._write(b"\xE0\x00")  # DISCONNECT
        except OSError:
            pass
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
            self.sock = None
