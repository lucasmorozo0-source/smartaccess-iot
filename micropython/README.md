# Portão Eletrônico IoT — Firmware MicroPython (ESP32)

Migração do firmware C (`sketch.ino`) para **MicroPython**, com:

- **Voz** via Google Home (Gemini for Home) → **Sinric Pro** → ESP32 → relé do portão
- **ThingsBoard** para dashboard + alertas push
- Concorrência com **`_thread`** (requisito do trabalho)

```
Voz → Google Home (Gemini) → Sinric Pro (WebSocket) → ESP32 → Relé
ESP32 → MQTT → ThingsBoard (dashboard + rule chain de alertas)
```

## Arquivos

| Arquivo         | Função                                                              |
|-----------------|---------------------------------------------------------------------|
| `config.py`     | **Único arquivo a editar**: WiFi, credenciais, pinos, senha         |
| `sinricpro.py`  | Cliente Sinric Pro (WebSocket + HMAC-SHA256, escritos do zero)      |
| `main.py`       | Threads, relé, teclado, LCD, telemetria                             |

As credenciais do seu dispositivo Sinric Pro **já estão preenchidas** em `config.py`.

## Threads

- **Thread 1** — Sinric Pro: WebSocket bloqueante, recebe `setPowerState` da voz e aciona o relé.
- **Thread 2** — ThingsBoard: publica telemetria a cada 10 s e escuta RPC (botão do dashboard).
- **Main** — teclado matricial + LCD + watchdog.

## Pré-requisitos

### 1. Gravar o MicroPython no ESP32
Baixe o firmware em https://micropython.org/download/esp32/ e grave:
```bash
pip install esptool
esptool --port COM5 erase_flash
esptool --port COM5 write_flash 0x1000 esp32-XXXXXXXX.bin
```

### 2. Instalar a biblioteca MQTT (para o ThingsBoard)
Com o ESP32 já conectado ao WiFi, no REPL:
```python
import mip
mip.install("umqtt.simple")
```
(Sem ela, a parte de voz funciona normalmente; só a telemetria fica desativada.)

### 3. (Opcional) Driver do LCD I2C
Se for usar o LCD 16x2/20x4 I2C, copie para o ESP32 os arquivos
`lcd_api.py` e `esp32_i2c_lcd.py` (projeto *Dave Hylands python_lcd*).
Sem eles, o firmware imprime no console e segue rodando.

### 4. Enviar os arquivos
Use **Thonny** (Run → Files) ou `mpremote`:
```bash
pip install mpremote
mpremote connect COM5 fs cp config.py sinricpro.py main.py :
```

## Configurar o `config.py`

Edite **só** estes campos:
```python
WIFI_SSID = "..."          # sua rede 2.4 GHz
WIFI_PASS = "..."
TB_TOKEN  = "..."          # Access Token do device no ThingsBoard
```
As credenciais do Sinric e os pinos já estão definidos.

## ThingsBoard — dashboard + alertas push

1. **Devices → +Add → Add new device** → nome `Portao`. Abra o device → *Copy access token* e cole em `TB_TOKEN`.
2. O ESP32 publica telemetria: `portao`, `ultimo_evento`, `acessos_ok`, `acessos_negados`, `tentativas` e, em eventos, `alerta`/`mensagem`.
3. **Dashboard**: crie um dashboard novo, adicione widgets (cards) ligados a essas keys.
4. **Botão remoto** (RPC): adicione um *Control widget* (ex.: "Switch/Button") com método `openGate` → o relé dá pulso.
5. **Alertas push** (Rule Chain):
   - Rule Chains → *Root Rule Chain*.
   - Após o nó *Message Type Switch* (saída **Post telemetry**), adicione um nó **filter → script**:
     ```js
     return msg.alerta === "negado";
     ```
   - Ligue a saída `True` a um nó **action → send notification** (ou *Push notification* / e-mail / Telegram), com a mensagem `${mensagem}`.
   - Faça o mesmo para `msg.alerta === "abertura"` se quiser avisar toda abertura.

## Testar a voz (a "camada de IA")

1. App **Google Home** → adicionar dispositivo → **Funciona com o Google** → procure **Sinric Pro** e faça login com a mesma conta.
2. O dispositivo "Portão" aparece. Diga: *"Ok Google, ligar o Portão"* ou *"abrir o Portão"*.
3. O Gemini for Home interpreta a linguagem natural, o Sinric Pro entrega o comando via WebSocket e o ESP32 dá o pulso no relé.

> Observação do trabalho: o Gemini **não** é integrado manualmente — o Google Home já o usa nativamente. A camada de IA é demonstrada pelos comandos em linguagem natural sendo processados.

## Observações sobre `_thread` no ESP32

- `_thread` no ESP32/MicroPython é funcional mas limitado (heap e GIL). O acesso ao relé e ao estado compartilhado é protegido por **locks**; o **watchdog** (20 s) reinicia se algo travar.
- Se faltar memória ao subir as duas threads, reduza buffers ou rode o ThingsBoard com intervalo maior (`TELEMETRY_INTERVAL_S`).
