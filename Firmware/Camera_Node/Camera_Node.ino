#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ESPmDNS.h>
#include <WiFiUdp.h>

#define CAMERA_MODEL_ESP32S3_EYE
#include "camera_pins.h"

const char* AP_SSID     = "SmartTrash-CAM";   // Tên hotspot khi cấu hình
const char* AP_PASS     = "12345678";         // Mật khẩu hotspot (tối thiểu 8 ký tự)
const char* hostname    = "esp32-cam";
const int   WIFI_TIMEOUT = 15;               // Timeout kết nối WiFi (giây)

WiFiUDP udp;
const int UDP_PORT = 8888;

Preferences prefs;
WebServer   configServer(80);  // Server tạm cho trang cấu hình WiFi

void startCameraServer();
void setupLedFlash(int pin);
const char CONFIG_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SmartTrash CAM - Cấu hình WiFi</title>
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
    button { width: 100%; padding: 14px; border-radius: 8px; border: none; background: #6366f1;
             color: white; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 24px; }
    button:hover { background: #4f46e5; }
    .info { background: #16213e; border-radius: 8px; padding: 12px; margin-top: 20px;
            font-size: 12px; color: #94a3b8; line-height: 1.6; }
    .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
           background: #22c55e; margin-right: 6px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon"></div>
    <h1>SmartTrash Camera</h1>
    <p class="sub">Cấu hình kết nối WiFi</p>
    <form action="/save" method="GET">
      <label>Tên WiFi (SSID)</label>
      <input type="text" name="ssid" placeholder="Nhập tên WiFi..." required>
      <label>Mật khẩu</label>
      <input type="password" name="pass" placeholder="Nhập mật khẩu WiFi..." required>
      <button type="submit"> Lưu & Kết Nối</button>
    </form>
    <div class="info">
      <span class="dot"></span>Sau khi lưu, thiết bị sẽ tự khởi động lại và kết nối WiFi mới.<br>
      <span class="dot"></span>Nếu WiFi sai, hotspot sẽ tự xuất hiện lại để bạn cấu hình lại.
    </div>
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
    .card { background: #1a1a2e; border-radius: 16px; padding: 40px; text-align: center;
            width: 90%; max-width: 400px; }
    .icon { font-size: 64px; margin-bottom: 16px; }
    h1 { color: #22c55e; margin-bottom: 12px; }
    p { color: #94a3b8; font-size: 14px; }
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

void handleConfigRoot() {
  configServer.send(200, "text/html", CONFIG_PAGE);
}

void handleConfigSave() {
  String ssid = configServer.hasArg("ssid") ? configServer.arg("ssid") : "";
  String pass = configServer.hasArg("pass") ? configServer.arg("pass") : "";

  Serial.printf("[WIFI] Dang xu ly luu... SSID: %s\n", ssid.c_str());

  if (ssid.length() > 0) {
    prefs.begin("wifi", false);
    prefs.putString("ssid", ssid);
    prefs.putString("pass", pass);
    prefs.end();

    configServer.send(200, "text/html", SAVE_PAGE);
    Serial.println("[OK] Da luu xong! May se khoi dong lai sau 2 giay...");
    
    configServer.client().stop();
    delay(2000);
    ESP.restart();
  } else {
    configServer.send(400, "text/plain", "SSID khong duoc de trong!");
  }
}

bool loadSavedWiFi(String &ssid, String &pass) {
  prefs.begin("wifi", true);  // read-only
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
  WiFi.setSleep(false);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < WIFI_TIMEOUT * 2) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[OK] Ket noi thanh cong! IP: %s\n", WiFi.localIP().toString().c_str());
    return true;
  }

  Serial.println("[FAIL] Khong the ket noi WiFi!");
  return false;
}

void startConfigPortal() {
  Serial.println("========================================");
  Serial.println("  CHE DO CAU HINH WIFI");
  Serial.printf("  Hotspot: %s\n", AP_SSID);
  Serial.printf("  Mat khau: %s\n", AP_PASS);
  Serial.println("  Truy cap: http://192.168.4.1");
  Serial.println("========================================");

  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  delay(500);

  configServer.on("/", handleConfigRoot);
  configServer.on("/save", handleConfigSave);
  configServer.begin();

  while (true) {
    configServer.handleClient();
    delay(10);

    if (Serial.available()) {
      String cmd = Serial.readStringUntil('\n');
      cmd.trim();
      if (cmd == "RESET") {
        clearSavedWiFi();
        ESP.restart();
      }
    }
  }
}


void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();
  Serial.println("========================================");
  Serial.println("  HE THONG PHAN LOAI RAC - CAMERA v2.1");
  Serial.println("========================================");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size   = FRAMESIZE_SVGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count     = 1;

  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 10;
      config.fb_count     = 2;
      config.grab_mode    = CAMERA_GRAB_LATEST;
      Serial.println("[OK] PSRAM detected - High quality mode");
    } else {
      config.frame_size  = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
      Serial.println("[WARN] No PSRAM - Limited quality mode");
    }
  } else {
    config.frame_size = FRAMESIZE_240X240;
#if CONFIG_IDF_TARGET_ESP32S3
    config.fb_count = 2;
#endif
  }

#if defined(CAMERA_MODEL_ESP_EYE)
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
#endif

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Camera init failed: 0x%x\n", err);
    return;
  }
  Serial.println("[OK] Camera initialized");

  sensor_t *s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_brightness(s, 1);
    s->set_saturation(s, -2);
  }
  if (config.pixel_format == PIXFORMAT_JPEG) {
    s->set_framesize(s, FRAMESIZE_SVGA);
  }

#if defined(CAMERA_MODEL_M5STACK_WIDE) || defined(CAMERA_MODEL_M5STACK_ESP32CAM)
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
#endif

#if defined(CAMERA_MODEL_ESP32S3_EYE)
  s->set_vflip(s, 1);
#endif

#if defined(LED_GPIO_NUM)
  setupLedFlash(LED_GPIO_NUM);
#endif

  String savedSSID, savedPass;
  bool hasSaved = loadSavedWiFi(savedSSID, savedPass);

  if (!hasSaved) {
    Serial.println("[WIFI] Chua co WiFi nao duoc luu!");
    startConfigPortal();  // Vào chế độ cấu hình (không return)
  }

  if (!connectWiFi(savedSSID, savedPass)) {
    Serial.println("[WIFI] WiFi da luu khong hop le, mo lai trang cau hinh...");
    startConfigPortal();  // Vào chế độ cấu hình
  }

  if (MDNS.begin(hostname)) {
    Serial.printf("[OK] mDNS: http://%s.local\n", hostname);
    MDNS.addService("http", "tcp", 80);
    MDNS.addService("http", "tcp", 81);
  }

  startCameraServer();

  udp.begin(UDP_PORT);
  Serial.printf("[UDP] Dang lang nghe Port %d cho Auto-Discovery\n", UDP_PORT);

  Serial.println("========================================");
  Serial.printf("  Stream: http://%s:81/stream\n", WiFi.localIP().toString().c_str());
  Serial.printf("  mDNS:   http://%s.local\n", hostname);
  Serial.println("  Gui 'RESET' qua Serial de doi WiFi");
  Serial.println("========================================");
}

void loop() {
  static unsigned long lastCheck = 0;
  if (millis() - lastCheck > 10000) {
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WARN] WiFi mat ket noi! Dang thu lai...");
      String ssid, pass;
      loadSavedWiFi(ssid, pass);
      if (!connectWiFi(ssid, pass)) {
        Serial.println("[ERROR] Khong the ket noi lai. Vao che do cau hinh...");
        startConfigPortal();
      }
    }
  }

  int packetSize = udp.parsePacket();
  if (packetSize) {
    char packetBuffer[255];
    int len = udp.read(packetBuffer, 255);
    if (len > 0) packetBuffer[len] = 0;
    
    if (strcmp(packetBuffer, "WHO_IS_TRASH_CAM") == 0) {
      String reply = "I_AM_TRASH_CAM|" + WiFi.localIP().toString();
      udp.beginPacket(udp.remoteIP(), udp.remotePort());
      udp.print(reply);
      udp.endPacket();
      Serial.println("[UDP] Da phan hoi Auto-Discovery cho PC!");
    }
  }

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "RESET") {
      clearSavedWiFi();
      Serial.println("[WIFI] Khoi dong lai de cau hinh WiFi moi...");
      delay(1000);
      ESP.restart();
    }
  }

  delay(10);
}
