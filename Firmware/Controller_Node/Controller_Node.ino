
#include <WiFi.h>
#include <WebServer.h>
#include <AccelStepper.h>
#include <ESP32Servo.h>
#include <Preferences.h>
#include <ESPmDNS.h>
#include <WiFiUdp.h>

const char* AP_SSID     = "SmartTrash-CTRL";
const char* AP_PASS     = "12345678";
const char* hostname    = "esp32-controller";
const int   WIFI_TIMEOUT = 15;

const int servoPin = 4;
const int stepPin  = 5;
const int dirPin   = 6;
const int enPin    = 7;
const int hallPin  = 15;
const int ledPin   = 2;

const float calibrationRatio = 150.0 / 130.0;
const long calibratedStepsPerRevolution = (long)(1600 * calibrationRatio);
const long steps90Degrees = calibratedStepsPerRevolution / 4;

#define SERVO_CLOSED  105
#define SERVO_OPEN    170

WiFiUDP udp;
const int UDP_PORT = 8888;
const char* AUTH_USER = "admin";
const char* AUTH_PASS = "SmartTrash2026";

Servo myServo;
AccelStepper stepper(AccelStepper::DRIVER, stepPin, dirPin);
Preferences prefs;
WebServer server(80);

enum SystemState {
  STATE_IDLE,
  STATE_HOMING,
  STATE_SORT_MOVING_TO_BIN,
  STATE_SORT_SERVO_OPENING,
  STATE_SORT_SERVO_CLOSING,
  STATE_SORT_FINISHING
};

SystemState currentState = STATE_IDLE;
int currentClassId = -1;
unsigned long stateTimer = 0;
int servoAngle = SERVO_CLOSED;
bool stepperEnabled = false;

unsigned long totalSorted = 0;
unsigned long sortCount[4] = {0};
const char* classNames[4] = {"Chai nuoc", "Lon nuoc ngot", "Thuoc la", "Vo keo"};
int sortCycleCounter = 0; 
const char CONFIG_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SmartTrash Controller - WiFi</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #0f0f1a; color: #f1f5f9;
           min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: #1a1a2e; border-radius: 16px; padding: 32px; width: 90%; max-width: 400px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
    h1 { text-align: center; font-size: 20px; margin-bottom: 8px; }
    .sub { text-align: center; color: #94a3b8; font-size: 13px; margin-bottom: 24px; }
    .icon { text-align: center; font-size: 48px; margin-bottom: 12px; }
    label { display: block; color: #94a3b8; font-size: 13px; margin-bottom: 6px; margin-top: 16px; }
    input { width: 100%; padding: 12px 16px; border-radius: 8px; border: 1px solid #2d2d4a;
            background: #16213e; color: #f1f5f9; font-size: 15px; outline: none; }
    input:focus { border-color: #6366f1; }
    button { width: 100%; padding: 14px; border-radius: 8px; border: none; background: #22c55e;
             color: white; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 24px; }
    button:hover { background: #16a34a; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon"></div>
    <h1>SmartTrash Controller</h1>
    <p class="sub">Cấu hình kết nối WiFi</p>
    <form action="/save" method="GET">
      <label>Tên WiFi (SSID)</label>
      <input type="text" name="ssid" placeholder="Nhập tên WiFi..." required>
      <label>Mật khẩu</label>
      <input type="password" name="pass" placeholder="Nhập mật khẩu WiFi..." required>
      <button type="submit"> Lưu & Kết Nối</button>
    </form>
  </div>
</body>
</html>
)rawliteral";

const char SAVE_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: 'Segoe UI', sans-serif; background: #0f0f1a; color: #f1f5f9;
           min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: #1a1a2e; border-radius: 16px; padding: 40px; text-align: center; width: 90%; max-width: 400px; }
    .icon { font-size: 64px; margin-bottom: 16px; }
    h1 { color: #22c55e; margin-bottom: 12px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon"></div>
    <h1>Đã lưu thành công!</h1>
    <p>Thiết bị đang khởi động lại...<br>Vui lòng đợi 10 giây.</p>
  </div>
</body>
</html>
)rawliteral";

bool loadSavedWiFi(String &ssid, String &pass) {
  prefs.begin("wifi", true);
  ssid = prefs.getString("ssid", "");
  pass = prefs.getString("pass", "");
  prefs.end();
  return ssid.length() > 0;
}

void clearSavedWiFi() {
  prefs.begin("wifi", false);
  prefs.clear();
  prefs.end();
  Serial.println("[WIFI] Da xoa thong tin WiFi!");
}

bool connectWiFi(const String &ssid, const String &pass) {
  Serial.printf("[WIFI] Dang ket noi: '%s'", ssid.c_str());
  WiFi.mode(WIFI_STA); 
  WiFi.disconnect();
  delay(100);
  WiFi.setHostname(hostname);
  WiFi.begin(ssid.c_str(), pass.c_str());

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < WIFI_TIMEOUT * 2) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[OK] IP: %s\n", WiFi.localIP().toString().c_str());
    return true;
  }
  Serial.println("[FAIL] Khong the ket noi WiFi!");
  return false;
}

void startConfigPortal() {
  Serial.println("========================================");
  Serial.println("  CHE DO CAU HINH WIFI");
  Serial.printf("  Hotspot: %s\n", AP_SSID);
  Serial.println("  Truy cap: http://192.168.4.1");
  Serial.println("========================================");

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  delay(500);

  WebServer apServer(80);
  apServer.on("/", HTTP_GET, [&apServer]() {
    apServer.send(200, "text/html", CONFIG_PAGE);
  });
  apServer.on("/save", [&apServer]() {
    String ssid = apServer.hasArg("ssid") ? apServer.arg("ssid") : "";
    String pass = apServer.hasArg("pass") ? apServer.arg("pass") : "";
    if (ssid.length() > 0) {
      Preferences p;
      p.begin("wifi", false);
      p.putString("ssid", ssid);
      p.putString("pass", pass);
      p.end();
      apServer.send(200, "text/html", SAVE_PAGE);
      apServer.client().stop(); // Đảm bảo gửi xong web mới restart
      delay(2000);
      ESP.restart();
    } else {
      apServer.send(400, "text/plain", "SSID khong duoc de trong!");
    }
  });
  apServer.begin();

  while (true) {
    apServer.handleClient();
    delay(10);
    if (Serial.available()) {
      if (Serial.readStringUntil('\n').indexOf("RESET") != -1) {
        clearSavedWiFi(); ESP.restart();
      }
    }
  }
}
void enableStepper(bool enable) {
  stepperEnabled = enable;
  digitalWrite(enPin, enable ? LOW : HIGH); // LOW = cấp điện, HIGH = ngắt điện
}

void sendJSON(int code, String jsonBody) {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(code, "application/json", jsonBody);
}

void handleStatus() {
  if (!server.authenticate(AUTH_USER, AUTH_PASS)) {
    return server.requestAuthentication();
  }

  String json = "{";
  json += "\"status\":\"ok\",";
  json += "\"state\":\"" + String(currentState) + "\",";
  json += "\"busy\":" + String(currentState != STATE_IDLE ? "true" : "false") + ",";
  json += "\"current_class\":" + String(currentClassId) + ",";
  json += "\"current_position\":" + String(stepper.currentPosition()) + ",";
  json += "\"total_sorted\":" + String(totalSorted) + ",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  json += "}";
  sendJSON(200, json);
}

void handleSort() {
  if (!server.authenticate(AUTH_USER, AUTH_PASS)) {
    return server.requestAuthentication();
  }

  if (currentState != STATE_IDLE) {
    sendJSON(503, "{\"status\":\"busy\",\"message\":\"Dang xu ly rac truoc do!\"}");
    return;
  }
  if (!server.hasArg("class")) {
    sendJSON(400, "{\"status\":\"error\",\"message\":\"Thieu tham so class\"}");
    return;
  }

  int class_id = server.arg("class").toInt();
  if (class_id < 0 || class_id > 3) {
    sendJSON(400, "{\"status\":\"error\",\"message\":\"Class khong hop le\"}");
    return;
  }

  currentClassId = class_id;
  long targetPosition = (long)class_id * steps90Degrees;
  enableStepper(true);
  stepper.moveTo(targetPosition);
  currentState = STATE_SORT_MOVING_TO_BIN;
  digitalWrite(ledPin, HIGH);
  
  Serial.printf("\n[SORT] Da nhan lenh Class %d. Dang chay ngam...\n", class_id);

  sendJSON(202, "{\"status\":\"accepted\",\"message\":\"Da dua vao hang doi xu ly\"}");
}

void handleHome() {
  if (!server.authenticate(AUTH_USER, AUTH_PASS)) {
    return server.requestAuthentication();
  }

  if (currentState != STATE_IDLE) {
    sendJSON(503, "{\"status\":\"busy\",\"message\":\"Dang xu ly viec khac!\"}");
    return;
  }
  
  enableStepper(true);
  stepper.setSpeed(500);
  stateTimer = millis();
  currentState = STATE_HOMING;
  digitalWrite(ledPin, HIGH);
  
  sendJSON(202, "{\"status\":\"accepted\",\"message\":\"Bat dau Homing\"}");
}


void processStateMachine() {
  switch (currentState) {
    case STATE_IDLE:
      if (stepperEnabled) {
        enableStepper(false); // Ngắt điện stepper hoàn toàn khi rảnh để tản nhiệt
      }
      break;

    case STATE_HOMING:
      stepper.runSpeed(); // Chạy vận tốc cố định
      if (digitalRead(hallPin) == LOW) { // Đã tìm thấy điểm gốc
        stepper.setCurrentPosition(0);
        stepper.moveTo(0);
        currentState = STATE_IDLE;
        digitalWrite(ledPin, LOW);
        Serial.println("[OK] Homing thanh cong!");
      } else if (millis() - stateTimer > 15000) { // Timeout 15s
        Serial.println("[ERROR] Homing timeout!");
        currentState = STATE_IDLE;
        digitalWrite(ledPin, LOW);
      }
      break;

    case STATE_SORT_MOVING_TO_BIN:
      stepper.run();
      if (stepper.distanceToGo() == 0) {
        myServo.write(SERVO_OPEN);
        stateTimer = millis();
        currentState = STATE_SORT_SERVO_OPENING;
      }
      break;

    case STATE_SORT_SERVO_OPENING:
      if (millis() - stateTimer >= 1000) { // Chờ 1s cho rác rơi
        servoAngle = SERVO_OPEN;
        stateTimer = millis();
        currentState = STATE_SORT_SERVO_CLOSING;
      }
      break;

    case STATE_SORT_SERVO_CLOSING:
      if (millis() - stateTimer >= 10) { // Cứ 10ms đóng 1 độ (Smooth Close)
        servoAngle--;
        myServo.write(servoAngle);
        stateTimer = millis();
        if (servoAngle <= SERVO_CLOSED) {
          stepper.moveTo(0); // Quay khay về vị trí đón rác ban đầu (góc 0)
          currentState = STATE_SORT_FINISHING;
        }
      }
      break;

    case STATE_SORT_FINISHING:
      stepper.run();
      if (stepper.distanceToGo() == 0) {
        totalSorted++;
        sortCount[currentClassId]++;
        sortCycleCounter++;
        currentClassId = -1;
        digitalWrite(ledPin, LOW);
        
        if (sortCycleCounter >= 50) {
           sortCycleCounter = 0;
           Serial.println("[AUTO] Kich hoat Auto-Homing de triet tieu sai so...");
           stepper.setSpeed(500);
           stateTimer = millis();
           currentState = STATE_HOMING;
           digitalWrite(ledPin, HIGH);
        } else {
           currentState = STATE_IDLE;
        }
      }
      break;
  }
}
void setup() {
  Serial.begin(115200);
  
  pinMode(enPin, OUTPUT);
  enableStepper(false); // Ngắt điện mặc định
  pinMode(hallPin, INPUT_PULLUP);
  pinMode(ledPin, OUTPUT); digitalWrite(ledPin, LOW);

  ESP32PWM::allocateTimer(0);
  myServo.setPeriodHertz(50);
  myServo.attach(servoPin, 500, 2500);
  myServo.write(SERVO_CLOSED);

  stepper.setMaxSpeed(2000.0);
  stepper.setAcceleration(1000.0);

  String savedSSID, savedPass;
  if (!loadSavedWiFi(savedSSID, savedPass) || !connectWiFi(savedSSID, savedPass)) {
    startConfigPortal();
  }

  if (MDNS.begin(hostname)) {
    MDNS.addService("http", "tcp", 80);
  }

  if (WiFi.status() == WL_CONNECTED) {
    udp.begin(UDP_PORT);
    Serial.printf("[UDP] Dang lang nghe Port %d cho Auto-Discovery\n", UDP_PORT);
  }

  Serial.println("[HOME] Dang tim diem goc...");
  enableStepper(true);
  stepper.setSpeed(500);

  unsigned long timeout = millis() + 15000;
bool homingOk = false;

while (millis() < timeout) {
  stepper.runSpeed();

  if (digitalRead(hallPin) == LOW) {
    homingOk = true;
    break;
  }

  server.handleClient(); // vẫn cho web server phản hồi trong lúc homing
}

if (homingOk) {
  stepper.setCurrentPosition(0);
  Serial.println("[OK] Homing thanh cong. San sang!");
} else {
  Serial.println("[ERROR] Homing timeout khi khoi dong. Kiem tra cam bien Hall!");
  stepper.setCurrentPosition(0); 
  
}

enableStepper(false);
  server.on("/sort", HTTP_GET, handleSort);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/home", HTTP_GET, handleHome);
  server.begin();
}

void loop() {
  server.handleClient();
  processStateMachine(); // Gọi máy trạng thái mỗi chu kỳ

  int packetSize = udp.parsePacket();
  if (packetSize) {
    char packetBuffer[255];
    int len = udp.read(packetBuffer, 255);
    if (len > 0) packetBuffer[len] = 0;
    
    if (strcmp(packetBuffer, "WHO_IS_TRASH_CTRL") == 0) {
      String reply = "I_AM_TRASH_CTRL|" + WiFi.localIP().toString();
      udp.beginPacket(udp.remoteIP(), udp.remotePort());
      udp.print(reply);
      udp.endPacket();
      Serial.println("[UDP] Da phan hoi Auto-Discovery cho PC!");
    }
  }

  static unsigned long lastCheck = 0;
  if (millis() - lastCheck > 30000) {
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      String ssid, pass; loadSavedWiFi(ssid, pass);
      if (!connectWiFi(ssid, pass)) startConfigPortal();
    }
  }

  if (Serial.available()) {
    if (Serial.readStringUntil('\n').indexOf("RESET") != -1) {
      clearSavedWiFi(); ESP.restart();
    }
  }
}
