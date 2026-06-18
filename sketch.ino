#include <Keypad.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <LiquidCrystal.h>

// >>> ADICIONADO: Sinric Pro (controle por voz via Google Home)
#include "SinricPro.h"
#include "SinricProSwitch.h"
// <<<

// WIFI
const char* ssid = "POCO X6 Pro 5G";
const char* passwordWifi = "dani12345";

// >>> ADICIONADO: credenciais do dispositivo "Portao" no Sinric Pro
#define SINRIC_APP_KEY    "14c9159a-2b8a-49b2-992e-dd9f1c208e89"
#define SINRIC_APP_SECRET "71a907dc-f622-4471-b2a4-338b1c31b9d9-bbf4464c-0e12-4dcd-a91a-4d7fe55d2e15"
#define SINRIC_DEVICE_ID  "6a3317c609efd1746c0f508e"
// <<<

// MQTT
const char* mqtt_server = "broker.hivemq.com";
WiFiClient espClient;
PubSubClient client(espClient);

// >>> ADICIONADO: ThingsBoard (dashboard + alertas push)
const char* tb_server = "thingsboard.cloud";
const char* tb_token  = "0h6qr90m7fqeu24lbfbj";   // Access Token do device
WiFiClient tbWifiClient;
PubSubClient tbClient(tbWifiClient);
unsigned long tbUltimoEnvio = 0;
// <<<

// LCD: RS, E, D4, D5, D6, D7
// D7 movido do GPIO5 (strapping do C6, nao chaveia direito) para o GPIO10.
LiquidCrystal lcd(21, 22, 18, 19, 23, 10);

// TECLADO 3x4
#define ROW_NUM 4
#define COL_NUM 3

char keys[ROW_NUM][COL_NUM] = {
  {'1','2','3'},
  {'4','5','6'},
  {'7','8','9'},
  {'*','0','#'}
};

// MAPEAMENTO FINAL
byte row_pins[ROW_NUM] = {11, 4, 2, 15};
byte col_pins[COL_NUM] = {10, 12, 3};

Keypad keypad = Keypad(makeKeymap(keys), row_pins, col_pins, ROW_NUM, COL_NUM);

// LEDS
int ledVerde = 6;
int ledVermelho = 7;

// SENHA
String senhaAtual = "1234";
String input = "";

int tentativas = 0;

// =====================================================
// >>> ADICIONADO: SINRIC PRO (Google Home por voz)
// =====================================================

// Chamado automaticamente quando chega um comando de voz do Google Home.
// "abrir/ligar o Portao" -> state = true -> aciona a liberacao remota.
bool onPowerState(const String &deviceId, bool &state) {

  Serial.print("[Sinric] Comando de voz: ");
  Serial.println(state ? "ABRIR" : "FECHAR");

  if (state) {
    liberarRemoto();   // reaproveita a funcao de acesso remoto ja existente
  } else {
    // >>> ADICIONADO: comando "desligar/fechar" -> marca fechado no ThingsBoard
    enviarThingsBoard("{\"portao\":\"fechado\",\"evento\":\"FECHADO_REMOTO\"}");
    // <<<
  }

  return true;         // confirma para o Google Home que foi processado
}

void setupSinricPro() {

  SinricProSwitch &meuPortao = SinricPro[SINRIC_DEVICE_ID];
  meuPortao.onPowerState(onPowerState);

  SinricPro.begin(SINRIC_APP_KEY, SINRIC_APP_SECRET);

  Serial.println("Sinric Pro iniciado");
}
// <<<

// =====================================================
// >>> ADICIONADO: THINGSBOARD (telemetria + alertas push)
// =====================================================

void reconectarThingsBoard() {

  if (tbClient.connected()) return;

  // No ThingsBoard o usuario MQTT = Access Token do device; senha vazia.
  if (tbClient.connect("ESP32_Portao_TB", tb_token, NULL)) {
    Serial.println("ThingsBoard conectado");
    tbClient.publish("v1/devices/me/telemetry", "{\"status\":\"online\"}");
  } else {
    Serial.print("ThingsBoard falhou, rc=");
    Serial.println(tbClient.state());
  }
}

void enviarThingsBoard(const String &json) {

  if (!tbClient.connected()) {
    reconectarThingsBoard();
  }

  if (tbClient.connected()) {
    tbClient.publish("v1/devices/me/telemetry", json.c_str());
    Serial.print("[TB] enviado: ");
    Serial.println(json);
  }
}
// <<<

// =====================================================

void setup() {

  Serial.begin(115200);

  lcd.begin(16, 2);
  lcd.clear();

  pinMode(ledVerde, OUTPUT);
  pinMode(ledVermelho, OUTPUT);

  digitalWrite(ledVerde, LOW);
  digitalWrite(ledVermelho, LOW);

  mostrarMensagem("SmartAccess", "Iniciando...");

  conectarWiFi();

  client.setServer(mqtt_server, 1883);
  client.setCallback(callbackMQTT);

  setupSinricPro();   // >>> ADICIONADO: inicia a integracao por voz

  tbClient.setServer(tb_server, 1883);   // >>> ADICIONADO: ThingsBoard
  reconectarThingsBoard();               // >>> ADICIONADO

  mostrarMensagem("Digite senha", "");
}

// =====================================================

void loop() {

  if (!client.connected()) {
    reconectarMQTT();
  }

  client.loop();

  SinricPro.handle();   // >>> ADICIONADO: processa comandos de voz

  // >>> ADICIONADO: mantem o ThingsBoard conectado + telemetria periodica
  if (!tbClient.connected()) {
    reconectarThingsBoard();
  }
  tbClient.loop();

  if (millis() - tbUltimoEnvio > 10000) {
    tbUltimoEnvio = millis();
    String t = "{\"rssi\":" + String(WiFi.RSSI()) +
               ",\"uptime\":" + String(millis() / 1000) + "}";
    enviarThingsBoard(t);
  }
  // <<<

  // >>> DESATIVADO no ESP32-C6: a leitura do teclado usa o GPIO12, que neste
  // chip e a linha de dados do USB (USB D-). Escanear o teclado derruba o USB
  // e deixa o Serial mudo. Como a demonstracao e por voz, a leitura do teclado
  // fica desligada. Para reativar (em um ESP32 classico), descomente o bloco.
  //
  // char key = keypad.getKey();
  //
  // if (key) {
  //
  //   Serial.print("Tecla: ");
  //   Serial.println(key);
  //
  //   if (key == '#') {
  //
  //     verificarSenha();
  //
  //   } else if (key == '*') {
  //
  //     limparEntrada();
  //
  //   } else {
  //
  //     adicionarTecla(key);
  //   }
  // }
  // <<<
}

// =====================================================
// WIFI
// =====================================================

void conectarWiFi() {

  WiFi.begin(ssid, passwordWifi);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Conectando...");

  while (WiFi.status() != WL_CONNECTED) {

    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi conectado");

  Serial.print("IP ESP32: ");
  Serial.println(WiFi.localIP());

  mostrarMensagem("WiFi OK", "");

  delay(2000);
}

// =====================================================
// MQTT
// =====================================================

void reconectarMQTT() {

  while (!client.connected()) {

    Serial.print("MQTT...");

    String clientId = "ESP32_";
    clientId += String(random(0xffff), HEX);

    if (client.connect(clientId.c_str())) {

      Serial.println(" conectado");

      client.publish("smartaccess/status", "online");

      client.subscribe("smartaccess/comando");
      client.subscribe("smartaccess/senha");

    } else {

      Serial.print(" erro ");
      Serial.println(client.state());

      delay(2000);
    }
  }
}

void callbackMQTT(char* topic, byte* payload, unsigned int length) {

  String mensagem = "";

  for (int i = 0; i < length; i++) {
    mensagem += (char)payload[i];
  }

  Serial.print("MQTT recebido [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(mensagem);

  if (String(topic) == "smartaccess/comando") {

    if (mensagem == "LIBERAR") {

      liberarRemoto();
    }
  }

  if (String(topic) == "smartaccess/senha") {

    senhaAtual = mensagem;

    client.publish("smartaccess/status", "senha_alterada");

    mostrarMensagem("Senha alterada", "via Web");

    delay(10000);

    mostrarMensagem("Digite senha", "");
  }
}

// =====================================================
// TECLADO
// =====================================================

void adicionarTecla(char key) {

  input += key;

  client.publish("smartaccess/tecla", String(key).c_str());

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Senha:");

  lcd.setCursor(0, 1);

  for (int i = 0; i < input.length(); i++) {

    lcd.print("*");
  }
}

void limparEntrada() {

  input = "";

  client.publish("smartaccess/status", "entrada_limpa");

  mostrarMensagem("Entrada limpa", "");

  delay(10000);

  mostrarMensagem("Digite senha", "");
}

// =====================================================
// SENHA
// =====================================================

void verificarSenha() {

  if (input == senhaAtual) {

    acessoLiberado();

  } else {

    acessoNegado();
  }

  input = "";
}

void acessoLiberado() {

  tentativas = 0;

  digitalWrite(ledVerde, HIGH);
  digitalWrite(ledVermelho, LOW);

  client.publish("smartaccess/acesso", "OK");

  // >>> ADICIONADO: telemetria pro ThingsBoard
  enviarThingsBoard("{\"portao\":\"aberto\",\"evento\":\"ACESSO_OK\"}");
  // <<<

  mostrarMensagem("ACESSO OK", "Bem-vindo");

  Serial.println("Acesso liberado");

  delay(10000);

  digitalWrite(ledVerde, LOW);

  mostrarMensagem("Digite senha", "");
}

void acessoNegado() {

  tentativas++;

  digitalWrite(ledVerde, LOW);
  digitalWrite(ledVermelho, HIGH);

  client.publish("smartaccess/acesso", "ERRO");

  // >>> ADICIONADO: telemetria + alerta pro ThingsBoard
  enviarThingsBoard("{\"portao\":\"fechado\",\"evento\":\"ACESSO_NEGADO\",\"alerta\":\"Tentativa de acesso negada\"}");
  // <<<

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print("Senha errada");

  lcd.setCursor(0, 1);
  lcd.print("Tentativa ");
  lcd.print(tentativas);

  Serial.println("Acesso negado");

  delay(10000);

  digitalWrite(ledVermelho, LOW);

  mostrarMensagem("Digite senha", "");
}

// =====================================================
// ACESSO REMOTO
// =====================================================

void liberarRemoto() {

  tentativas = 0;

  digitalWrite(ledVerde, HIGH);
  digitalWrite(ledVermelho, LOW);

  mostrarMensagem("ACESSO REMOTO", "Liberado");

  client.publish("smartaccess/acesso", "REMOTO_OK");

  // >>> ADICIONADO: telemetria + alerta pro ThingsBoard (caminho da voz)
  enviarThingsBoard("{\"portao\":\"aberto\",\"evento\":\"REMOTO_OK\",\"alerta\":\"Portao aberto remotamente\"}");
  // <<<

  Serial.println("Acesso remoto liberado");

  delay(10000);

  digitalWrite(ledVerde, LOW);

  // >>> ADICIONADO: fim do pulso -> portao voltou a fechar
  enviarThingsBoard("{\"portao\":\"fechado\",\"evento\":\"FECHOU\"}");
  // <<<

  mostrarMensagem("Digite senha", "");
}

// =====================================================
// LCD
// =====================================================

void mostrarMensagem(String l1, String l2) {

  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print(l1);

  lcd.setCursor(0, 1);
  lcd.print(l2);
}
