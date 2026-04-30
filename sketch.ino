#include <Keypad.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ================== KEYPAD ==================
#define ROW_NUM 4
#define COL_NUM 4

char keys[ROW_NUM][COL_NUM] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};

// pinos seguros
byte row_pins[ROW_NUM] = {13, 12, 14, 27};
byte col_pins[COL_NUM] = {26, 25, 33, 32};

Keypad keypad = Keypad(makeKeymap(keys), row_pins, col_pins, ROW_NUM, COL_NUM);

// ================== LCD ==================
LiquidCrystal_I2C lcd(0x27, 20, 4);

// ================== LED ==================
int ledVerde = 4;
int ledVermelho = 16;

// ================== CONFIG ==================
String password = "1234";
String input = "";

int tentativas = 0;
unsigned long lastInputTime = 0;
const int timeout = 10000;

// ================== SETUP ==================
void setup() {
  Serial.begin(115200);

  lcd.init();
  lcd.backlight();

  pinMode(ledVerde, OUTPUT);
  pinMode(ledVermelho, OUTPUT);

  digitalWrite(ledVerde, LOW);
  digitalWrite(ledVermelho, LOW);

  mostrarMensagem("SmartAccess", "Digite senha");
}

// ================== LOOP ==================
void loop() {
  char key = keypad.getKey();

  // timeout
  if (millis() - lastInputTime > timeout && input.length() > 0) {
    input = "";
    mostrarMensagem("Tempo esgotado", "Digite novamente");
  }

  if (key) {
    lastInputTime = millis();

    if (key == '#') {
      verificarSenha();
    }
    else if (key == '*') {
      limparEntrada();
    }
    else {
      adicionarTecla(key);
    }
  }
}

// ================== FUNCOES ==================

void adicionarTecla(char key) {
  input += key;

  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print("Senha:");

  lcd.setCursor(0,1);

  for (int i = 0; i < input.length(); i++) {
    lcd.print("*");
  }
}

void limparEntrada() {
  input = "";
  mostrarMensagem("Entrada limpa", "Digite novamente");
}

void verificarSenha() {
  if (input == password) {
    acessoLiberado();
  } else {
    acessoNegado();
  }

  input = "";
}

// ================== RESULTADOS ==================

void acessoLiberado() {
  tentativas = 0;

  digitalWrite(ledVerde, HIGH);
  digitalWrite(ledVermelho, LOW);

  mostrarMensagem("ACESSO OK", "Bem-vindo");

  delay(2000);

  digitalWrite(ledVerde, LOW);

  mostrarMensagem("Digite senha", "");
}

void acessoNegado() {
  tentativas++;

  digitalWrite(ledVerde, LOW);
  digitalWrite(ledVermelho, HIGH);

  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print("Senha incorreta");

  lcd.setCursor(0,1);
  lcd.print("Tentativas: ");
  lcd.print(tentativas);

  delay(2000);

  digitalWrite(ledVermelho, LOW);

  if (tentativas >= 3) {
    lcd.clear();
    lcd.print("BLOQUEADO!");
    delay(3000);
    tentativas = 0;
  }

  mostrarMensagem("Digite senha", "");
}

// ================== LCD ==================

void mostrarMensagem(String l1, String l2) {
  lcd.clear();
  lcd.setCursor(0,0);
  lcd.print(l1);

  lcd.setCursor(0,1);
  lcd.print(l2);
}