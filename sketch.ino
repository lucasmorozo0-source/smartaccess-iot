#include <Keypad.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <LiquidCrystal.h>

// WIFI
const char* ssid = "SEU_WIFI";
const char* passwordWifi = "SUA_SENHA";

// MQTT
const char* mqtt_server = "broker.hivemq.com";
WiFiClient espClient;
PubSubClient client(espClient);

// LCD: RS, E, D4, D5, D6, D7
LiquidCrystal lcd(21, 22, 18, 19, 23, 5);

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

  mostrarMensagem("Digite senha", "");
}

// =====================================================

void loop() {

  if (!client.connected()) {
    reconectarMQTT();
  }

  client.loop();

  char key = keypad.getKey();

  if (key) {

    Serial.print("Tecla: ");
    Serial.println(key);

    if (key == '#') {

      verificarSenha();

    } else if (key == '*') {

      limparEntrada();

    } else {

      adicionarTecla(key);
    }
  }
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

  Serial.println("Acesso remoto liberado");

  delay(10000);

  digitalWrite(ledVerde, LOW);

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
