#include <Arduino.h>

#define TINY_GSM_MODEM_SIM800
#define TINY_GSM_RX_BUFFER 1024
#include <TinyGsmClient.h>
#include <ArduinoHttpClient.h>

// T-Call V1.3 modem pins
#define MODEM_RST       5
#define MODEM_PWKEY     4
#define MODEM_POWER_ON  23
#define MODEM_TX        27
#define MODEM_RX        26

#define SerialAT Serial1

// ---- CHANGE THIS to your carrier's APN ----
const char apn[]      = "YOUR_APN";
const char gprsUser[] = "";
const char gprsPass[] = "";

TinyGsm modem(SerialAT);
TinyGsmClient client(modem);
HttpClient http(client, "example.com", 80);

void powerOnModem() {
  pinMode(MODEM_PWKEY, OUTPUT);
  pinMode(MODEM_RST, OUTPUT);
  pinMode(MODEM_POWER_ON, OUTPUT);
  digitalWrite(MODEM_PWKEY, LOW);
  digitalWrite(MODEM_RST, HIGH);
  digitalWrite(MODEM_POWER_ON, HIGH);
}

bool connectInternet() {
  Serial.println("Waiting for network...");
  if (!modem.waitForNetwork(60000L)) {
    Serial.println("Network registration FAILED");
    return false;
  }
  Serial.print("Operator: ");  Serial.println(modem.getOperator());
  Serial.print("Signal (0-31): "); Serial.println(modem.getSignalQuality());

  Serial.print("Connecting to mobile data, APN: "); Serial.println(apn);
  if (!modem.gprsConnect(apn, gprsUser, gprsPass)) {
    Serial.println("GPRS connect FAILED (check APN / data plan)");
    return false;
  }
  Serial.print("Connected. Local IP: "); Serial.println(modem.localIP());
  return true;
}

bool testInternet() {
  Serial.println("Testing internet (GET example.com)...");
  http.connectionKeepAlive();
  int err = http.get("/");
  if (err != 0) {
    Serial.print("Request failed, error: "); Serial.println(err);
    http.stop();
    return false;
  }
  int status = http.responseStatusCode();
  Serial.print("HTTP status: "); Serial.println(status);
  http.stop();
  return status > 0;
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== ESP32 T-Call internet test ===");

  powerOnModem();
  SerialAT.begin(115200, SERIAL_8N1, MODEM_RX, MODEM_TX);
  delay(3000);

  Serial.println("Restarting modem...");
  if (!modem.restart()) {
    Serial.println("Modem not responding (try baud 9600, check power)");
  }
  Serial.print("Modem: "); Serial.println(modem.getModemInfo());

  int sim = modem.getSimStatus();
  Serial.print("SIM status (3 = ready): "); Serial.println(sim);

  if (connectInternet()) testInternet();
}

void loop() {
  if (!modem.isGprsConnected()) {
    Serial.println("Internet lost, reconnecting...");
    connectInternet();
  } else {
    Serial.println("Online");
  }
  delay(30000);
}
