# ============================================================
# main.py  -  Portao Eletronico IoT (MicroPython / ESP32)
#
# Arquitetura:
#   Voz -> Google Home (Gemini) -> Sinric Pro -> ESP32 -> Rele (portao)
#   ESP32 -> MQTT -> ThingsBoard (dashboard + alertas push)
#
# Concorrencia com _thread (requisito do trabalho):
#   Thread 1 : Sinric Pro (WebSocket, loop bloqueante) -> comando de voz
#   Thread 2 : Telemetria + RPC do ThingsBoard (MQTT)
#   Main     : teclado matricial + LCD + watchdog
# ============================================================

import _thread
import network
import utime
import machine
from machine import Pin

import config
from sinricpro import SinricPro

try:
    import ntptime
except ImportError:
    ntptime = None

# umqtt.simple precisa estar instalado (ver README). Se faltar, a Thread 2
# avisa e segue sem ThingsBoard (a parte de voz continua funcionando).
try:
    from umqtt.simple import MQTTClient
except ImportError:
    MQTTClient = None

# LCD I2C e opcional: se nao tiver o driver, usa o console.
try:
    from machine import SoftI2C
    from esp32_i2c_lcd import I2cLcd
except ImportError:
    I2cLcd = None


# ============================================================
# Estado compartilhado entre as threads (protegido por lock)
# ============================================================
_lock = _thread.allocate_lock()

estado = {
    "portao": "fechado",      # fechado | aberto
    "ultimo_evento": "boot",
    "ultima_tecla": "-",
    "tentativas": 0,
    "senha": config.SENHA_INICIAL,
    "acessos_ok": 0,
    "acessos_negados": 0,
}

# Fila simples de alertas a publicar no ThingsBoard (consumida pela Thread 2)
_alertas = []

sinric = None   # referencia global ao cliente Sinric (preenchida no boot)


def set_estado(**kw):
    with _lock:
        estado.update(kw)


def push_alerta(tipo, msg):
    with _lock:
        _alertas.append({"tipo": tipo, "msg": msg, "ts": utime.time()})


# ============================================================
# Hardware
# ============================================================
relay = Pin(config.RELAY_PIN, Pin.OUT)
led_verde = Pin(config.LED_VERDE, Pin.OUT)
led_vermelho = Pin(config.LED_VERMELHO, Pin.OUT)

# valor "desligado" do rele depende se e ativo em LOW ou HIGH
_RELAY_OFF = 1 if config.RELAY_ACTIVE_LOW else 0
_RELAY_ON = 0 if config.RELAY_ACTIVE_LOW else 1
relay.value(_RELAY_OFF)
led_verde.value(0)
led_vermelho.value(0)

_relay_lock = _thread.allocate_lock()

lcd = None


def lcd_show(l1, l2=""):
    if lcd:
        try:
            lcd.clear()
            lcd.putstr(l1[:16])
            if l2:
                lcd.move_to(0, 1)
                lcd.putstr(l2[:16])
            return
        except Exception:
            pass
    print("LCD>", l1, "|", l2)


def pulso_portao(origem):
    """Aciona o rele por um pulso (abre/fecha o portao). Thread-safe."""
    with _relay_lock:
        set_estado(portao="aberto", ultimo_evento="abertura:%s" % origem)
        led_verde.value(1)
        led_vermelho.value(0)
        lcd_show("Portao", "ABRINDO (%s)" % origem)
        relay.value(_RELAY_ON)
        utime.sleep_ms(config.RELAY_PULSE_MS)
        relay.value(_RELAY_OFF)
        utime.sleep_ms(300)
        led_verde.value(0)
        set_estado(portao="fechado")
        lcd_show("Portao", "ok")
    push_alerta("abertura", "Portao acionado via %s" % origem)


# ============================================================
# Callback do Sinric (chamado pela Thread 1 quando chega voz)
# ============================================================
def on_voz(device_id, ligar):
    # Tipo Switch em modo "pulso": qualquer ON aciona o portao.
    if ligar:
        pulso_portao("voz/Google Home")
    return True


# ============================================================
# Thread 2 - ThingsBoard (telemetria + RPC)
# ============================================================
def on_rpc(topic, msg):
    # ThingsBoard manda comandos por v1/devices/me/rpc/request/<id>
    try:
        import ujson
        data = ujson.loads(msg)
        metodo = data.get("method", "")
        if metodo in ("setGate", "openGate", "liberar"):
            pulso_portao("dashboard/ThingsBoard")
        elif metodo == "setSenha":
            nova = str(data.get("params", ""))
            if nova:
                set_estado(senha=nova)
    except Exception as e:
        print("[TB] erro RPC:", e)


def thread_thingsboard():
    if MQTTClient is None:
        print("[TB] umqtt.simple ausente -> telemetria desativada. Ver README.")
        return

    while True:
        try:
            cli = MQTTClient("esp32_portao", config.TB_HOST, port=config.TB_PORT,
                             user=config.TB_TOKEN, password="", keepalive=60)
            cli.set_callback(on_rpc)
            cli.connect()
            cli.subscribe(b"v1/devices/me/rpc/request/+")
            print("[TB] conectado ao ThingsBoard")
            push_alerta("sistema", "ESP32 online")

            t0 = utime.ticks_ms()
            while True:
                cli.check_msg()  # nao-bloqueante: processa RPC pendente

                # publica telemetria periodica
                if utime.ticks_diff(utime.ticks_ms(), t0) >= config.TELEMETRY_INTERVAL_S * 1000:
                    t0 = utime.ticks_ms()
                    with _lock:
                        tele = {
                            "portao": estado["portao"],
                            "ultimo_evento": estado["ultimo_evento"],
                            "ultima_tecla": estado["ultima_tecla"],
                            "tentativas": estado["tentativas"],
                            "acessos_ok": estado["acessos_ok"],
                            "acessos_negados": estado["acessos_negados"],
                        }
                    import ujson
                    cli.publish(b"v1/devices/me/telemetry", ujson.dumps(tele))

                # despacha alertas acumulados (cada um vira um ponto de telemetria
                # que a rule chain do ThingsBoard transforma em push)
                with _lock:
                    pendentes = _alertas[:]
                    _alertas.clear()
                for a in pendentes:
                    import ujson
                    cli.publish(b"v1/devices/me/telemetry",
                                ujson.dumps({"alerta": a["tipo"], "mensagem": a["msg"]}))

                utime.sleep_ms(200)
        except Exception as e:
            print("[TB] desconectado (%s). Reconectando em 5s..." % e)
            utime.sleep(5)


# ============================================================
# Teclado matricial (lido na thread principal)
# ============================================================
KEYS = [
    ["1", "2", "3"],
    ["4", "5", "6"],
    ["7", "8", "9"],
    ["*", "0", "#"],
]
_rows = [Pin(p, Pin.OUT) for p in config.KEYPAD_ROWS]
_cols = [Pin(p, Pin.IN, Pin.PULL_UP) for p in config.KEYPAD_COLS]
for r in _rows:
    r.value(1)


def ler_tecla():
    for ri, row in enumerate(_rows):
        row.value(0)
        for ci, col in enumerate(_cols):
            if col.value() == 0:
                # espera soltar (debounce simples)
                while col.value() == 0:
                    utime.sleep_ms(10)
                row.value(1)
                return KEYS[ri][ci]
        row.value(1)
    return None


def verificar_senha(entrada):
    with _lock:
        ok = entrada == estado["senha"]
    if ok:
        with _lock:
            estado["acessos_ok"] += 1
            estado["tentativas"] = 0
        pulso_portao("teclado")
        if sinric:
            sinric.report_power_state(True)   # avisa o Google Home
    else:
        with _lock:
            estado["acessos_negados"] += 1
            estado["tentativas"] += 1
            t = estado["tentativas"]
        led_vermelho.value(1)
        lcd_show("Senha errada", "Tentativa %d" % t)
        push_alerta("negado", "Senha incorreta (tentativa %d)" % t)
        utime.sleep(2)
        led_vermelho.value(0)
        lcd_show("Digite a senha")


# ============================================================
# Boot
# ============================================================
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        lcd_show("Conectando", "WiFi...")
        wlan.connect(config.WIFI_SSID, config.WIFI_PASS)
        t = 0
        while not wlan.isconnected() and t < 30:
            utime.sleep(1)
            t += 1
            print(".", end="")
    if wlan.isconnected():
        print("\nWiFi OK:", wlan.ifconfig()[0])
        lcd_show("WiFi OK", wlan.ifconfig()[0])
        return True
    print("\nFalha no WiFi")
    lcd_show("WiFi FALHOU")
    return False


def sincronizar_relogio():
    if ntptime is None:
        return
    for _ in range(3):
        try:
            ntptime.settime()
            print("Relogio sincronizado (NTP)")
            return
        except Exception:
            utime.sleep(1)
    print("NTP falhou (Sinric pode rejeitar assinatura)")


def init_lcd():
    global lcd
    if I2cLcd is None:
        return
    try:
        i2c = SoftI2C(scl=Pin(config.LCD_SCL), sda=Pin(config.LCD_SDA))
        lcd = I2cLcd(i2c, config.LCD_ADDR, config.LCD_ROWS, config.LCD_COLS)
    except Exception as e:
        print("LCD indisponivel:", e)


def main():
    global sinric

    init_lcd()
    lcd_show("SmartAccess", "Iniciando...")

    if not conectar_wifi():
        # sem rede nao adianta seguir; reinicia
        utime.sleep(5)
        machine.reset()

    sincronizar_relogio()

    # ---- Thread 1: Sinric Pro (voz) ----
    sinric = SinricPro(
        app_key=config.SINRIC_APP_KEY,
        app_secret=config.SINRIC_APP_SECRET,
        device_ids=[config.SINRIC_DEVICE_ID],
        host=config.SINRIC_HOST,
        port=config.SINRIC_PORT,
        on_power_state=on_voz,
    )
    _thread.start_new_thread(sinric.run_forever, ())

    # ---- Thread 2: ThingsBoard (telemetria + RPC) ----
    _thread.start_new_thread(thread_thingsboard, ())

    # ---- Main: teclado ----
    wdt = machine.WDT(timeout=20000)   # watchdog: reinicia se travar
    lcd_show("Digite a senha")
    buffer = ""
    while True:
        wdt.feed()
        tecla = ler_tecla()
        if tecla:
            set_estado(ultima_tecla=tecla)
            if tecla == "#":
                verificar_senha(buffer)
                buffer = ""
            elif tecla == "*":
                buffer = ""
                lcd_show("Digite a senha")
            else:
                buffer += tecla
                lcd_show("Senha:", "*" * len(buffer))
        utime.sleep_ms(50)


main()
