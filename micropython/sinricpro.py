# ============================================================
# sinricpro.py  -  Cliente Sinric Pro para MicroPython (ESP32)
#
# O Sinric Pro nao tem SDK oficial para MicroPython, entao este modulo
# implementa o minimo necessario:
#   - Cliente WebSocket (handshake + framing + mascara de cliente)
#   - HMAC-SHA256 na mao (MicroPython nao tem o modulo 'hmac')
#   - Assinatura/validacao das mensagens do protocolo Sinric
#
# Fluxo: Google Home (Gemini) -> Sinric Pro -> ESP32 (este cliente)
# ============================================================

import usocket as socket
import ustruct as struct
import uselect
import ubinascii
import uhashlib
import ujson
import utime
import os


# ---------- HMAC-SHA256 (manual) ----------
def _hmac_sha256(key, msg):
    block = 64
    if len(key) > block:
        key = uhashlib.sha256(key).digest()
    key = key + b"\x00" * (block - len(key))
    o_key = bytes(b ^ 0x5C for b in key)
    i_key = bytes(b ^ 0x36 for b in key)
    inner = uhashlib.sha256(i_key + msg).digest()
    return uhashlib.sha256(o_key + inner).digest()


def _b64(data):
    return ubinascii.b2a_base64(data).strip().decode()


# Epoch: ESP32/MicroPython conta segundos a partir de 2000-01-01.
# Unix conta a partir de 1970-01-01. Diferenca = 946684800 s.
_EPOCH_OFFSET = 946684800


def _unix_now():
    return utime.time() + _EPOCH_OFFSET


# ---------- WebSocket minimo ----------
class _WS:
    def __init__(self, host, port, headers):
        self.host = host
        self.port = port
        self.headers = headers
        self.sock = None
        self.poller = None

    def connect(self):
        addr = socket.getaddrinfo(self.host, self.port)[0][-1]
        self.sock = socket.socket()
        self.sock.connect(addr)

        key = _b64(os.urandom(16))
        req = "GET / HTTP/1.1\r\n"
        req += "Host: %s\r\n" % self.host
        req += "Upgrade: websocket\r\n"
        req += "Connection: Upgrade\r\n"
        req += "Sec-WebSocket-Key: %s\r\n" % key
        req += "Sec-WebSocket-Version: 13\r\n"
        for k, v in self.headers:
            req += "%s: %s\r\n" % (k, v)
        req += "\r\n"
        self.sock.send(req.encode())

        # Le a resposta do handshake ate o fim dos headers
        resp = b""
        while b"\r\n\r\n" not in resp:
            ch = self.sock.recv(1)
            if not ch:
                raise OSError("handshake fechado")
            resp += ch
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            raise OSError("handshake falhou: %s" % resp[:64])

        self.poller = uselect.poll()
        self.poller.register(self.sock, uselect.POLLIN)

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise OSError("conexao fechada")
            buf += chunk
        return buf

    def has_data(self, timeout_ms):
        return bool(self.poller.poll(timeout_ms))

    def read_frame(self):
        # Retorna (opcode, bytes). Frames do servidor NAO sao mascarados.
        b1, b2 = self._recv_exact(2)
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        data = self._recv_exact(length) if length else b""
        if masked:
            data = bytes(data[i] ^ mask[i % 4] for i in range(len(data)))
        return opcode, data

    def send(self, data, opcode=0x1):
        if isinstance(data, str):
            data = data.encode()
        n = len(data)
        frame = bytearray()
        frame.append(0x80 | opcode)            # FIN + opcode
        if n < 126:
            frame.append(0x80 | n)             # MASK + len
        elif n < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack(">H", n))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack(">Q", n))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(data[i] ^ mask[i % 4] for i in range(n)))
        self.sock.send(frame)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ---------- Cliente Sinric Pro ----------
class SinricPro:
    """
    on_power_state(device_id, state_bool) -> bool
        callback chamado quando chega comando de voz.
        Deve retornar True se conseguiu executar (vira success no ACK).
    """

    def __init__(self, app_key, app_secret, device_ids,
                 host="ws.sinric.pro", port=80, on_power_state=None, log=print):
        self.app_key = app_key
        self.secret = app_secret.encode()
        self.device_ids = device_ids if isinstance(device_ids, list) else [device_ids]
        self.host = host
        self.port = port
        self.on_power_state = on_power_state
        self.log = log
        self.ws = None

    def _headers(self):
        return [
            ("appkey", self.app_key),
            ("deviceids", ";".join(self.device_ids)),
            ("restoredevicestates", "false"),
            ("platform", "micropython"),
        ]

    def connect(self):
        self.log("[Sinric] conectando em %s:%d ..." % (self.host, self.port))
        self.ws = _WS(self.host, self.port, self._headers())
        self.ws.connect()
        self.log("[Sinric] conectado (WebSocket OK)")

    # ---- assinatura ----
    def _sign(self, payload_str):
        return _b64(_hmac_sha256(self.secret, payload_str.encode()))

    def _wrap(self, payload):
        # Assina a string EXATA que sera enviada (evita problema de ordem de chaves)
        payload_str = ujson.dumps(payload)
        sig = self._sign(payload_str)
        return ('{"header":{"payloadVersion":2,"signatureVersion":1},'
                '"payload":' + payload_str +
                ',"signature":{"HMAC":"' + sig + '"}}')

    # ---- respostas / eventos ----
    def _send_response(self, req_payload, success, state):
        resp = {
            "action": req_payload.get("action"),
            "clientId": req_payload.get("clientId"),
            "createdAt": _unix_now(),
            "deviceId": req_payload.get("deviceId"),
            "message": "OK" if success else "ERRO",
            "replyToken": req_payload.get("replyToken"),
            "success": success,
            "type": "response",
            "value": {"state": "On" if state else "Off"},
        }
        self.ws.send(self._wrap(resp))

    def report_power_state(self, state):
        """Avisa o Sinric/Google Home de uma mudanca feita localmente (teclado)."""
        if not self.ws:
            return
        evt = {
            "action": "setPowerState",
            "cause": {"type": "PHYSICAL_INTERACTION"},
            "createdAt": _unix_now(),
            "deviceId": self.device_ids[0],
            "replyToken": _b64(os.urandom(12)),
            "type": "event",
            "value": {"state": "On" if state else "Off"},
        }
        try:
            self.ws.send(self._wrap(evt))
        except Exception as e:
            self.log("[Sinric] falha ao reportar estado: %s" % e)

    # ---- tratamento de mensagem ----
    def _handle(self, raw):
        try:
            msg = ujson.loads(raw)
        except Exception:
            return
        if "timestamp" in msg and "payload" not in msg:
            return  # keep-alive / sync de tempo do servidor
        payload = msg.get("payload", {})
        action = payload.get("action")
        if action == "setPowerState" and payload.get("type") == "request":
            state = payload.get("value", {}).get("state") == "On"
            dev = payload.get("deviceId")
            self.log("[Sinric] comando de voz: %s -> %s" %
                     (dev, "ON" if state else "OFF"))
            ok = True
            if self.on_power_state:
                try:
                    ok = bool(self.on_power_state(dev, state))
                except Exception as e:
                    self.log("[Sinric] erro no callback: %s" % e)
                    ok = False
            self._send_response(payload, ok, state)

    # ---- loop principal (Thread 1) ----
    def run_forever(self):
        while True:
            try:
                if not self.ws:
                    self.connect()
                if self.ws.has_data(200):
                    opcode, data = self.ws.read_frame()
                    if opcode == 0x8:               # close
                        raise OSError("close frame")
                    elif opcode == 0x9:             # ping -> pong
                        self.ws.send(data, opcode=0xA)
                    elif opcode in (0x1, 0x2):      # text / binary
                        self._handle(data)
            except Exception as e:
                self.log("[Sinric] desconectado (%s). Reconectando em 5s..." % e)
                if self.ws:
                    self.ws.close()
                self.ws = None
                utime.sleep(5)
