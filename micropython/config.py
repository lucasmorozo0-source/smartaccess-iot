# ============================================================
# config.py  -  SmartAccess IoT / Portao Eletronico (MicroPython)
# Centraliza credenciais e pinos. Edite SOMENTE este arquivo.
# ============================================================

# ---------- WiFi ----------
WIFI_SSID = "POCO X6 Pro 5G"
WIFI_PASS = "dani12345"

# ---------- Sinric Pro (Google Home por voz) ----------
# Credenciais do dispositivo "Portao" (tipo Switch) no painel sinric.pro
SINRIC_APP_KEY    = "14c9159a-2b8a-49b2-992e-dd9f1c208e89"
SINRIC_APP_SECRET = "71a907dc-f622-4471-b2a4-338b1c31b9d9-bbf4464c-0e12-4dcd-a91a-4d7fe55d2e15"
SINRIC_DEVICE_ID  = "6a3317c609efd1746c0f508e"

SINRIC_HOST = "ws.sinric.pro"
SINRIC_PORT = 80          # WebSocket sem TLS (mais leve no ESP32)

# ---------- ThingsBoard (dashboard + alertas push) ----------
# Crie um device no ThingsBoard e cole o "Access Token" dele aqui.
TB_HOST  = "demo.thingsboard.io"   # ou thingsboard.cloud / seu servidor
TB_PORT  = 1883
TB_TOKEN = "COLE_O_ACCESS_TOKEN_DO_THINGSBOARD"

# ---------- Pinos (conforme diagram.json do Wokwi) ----------
# Rele do portao: dispara um pulso e volta sozinho (botao do controle)
RELAY_PIN        = 5
RELAY_ACTIVE_LOW = True     # modulos rele azuis costumam ser ativos em LOW
RELAY_PULSE_MS   = 1000     # duracao do pulso (abre/fecha)

LED_VERDE   = 4
LED_VERMELHO = 16

# Teclado matricial 3x4 (4 linhas, 3 colunas usadas)
KEYPAD_ROWS = [13, 12, 14, 27]
KEYPAD_COLS = [26, 25, 33]      # diagram tem C1..C4; usamos 3 colunas

# LCD I2C (opcional). Se nao tiver driver, o firmware ignora e usa o console.
LCD_SDA  = 21
LCD_SCL  = 22
LCD_ADDR = 0x27
LCD_COLS = 16
LCD_ROWS = 2

# ---------- Senha do portao (acesso local pelo teclado) ----------
SENHA_INICIAL = "1234"

# ---------- Telemetria ----------
TELEMETRY_INTERVAL_S = 10   # de quanto em quanto tempo publica no ThingsBoard
