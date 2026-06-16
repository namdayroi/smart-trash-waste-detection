#include <WiFi.h>
#include <WebServer.h>
#include <AccelStepper.h>
#include <ESP32Servo.h>

// 1. Cấu hình Wi-Fi
const char* ssid = "Realme Q5";     // Thay bằng tên Wi-Fi nhà bạn
const char* password = "999999999";    // Thay bằng mật khẩu Wi-Fi

// Khởi tạo WebServer ở cổng 80
WebServer server(80);

// 2. Khai báo chân
const int servoPin = 4;    
const int stepPin  = 5;    
const int dirPin   = 6;    
const int enPin    = 7;    
const int hallPin  = 15;   

// 3. Thông số kỹ thuật
const float gearRatio = 150.0 / 130.0;
const long stepsPerRevolution = (long)(1600 * gearRatio); 
const long steps90Degrees = stepsPerRevolution / 4; 

#define SERVO_START 110   
#define SERVO_OPEN  170   

Servo myServo;
AccelStepper stepper(AccelStepper::DRIVER, stepPin, dirPin);

// Hàm xử lý khi nhận được lệnh từ máy tính qua Wi-Fi
void handleSort() {
  // Kiểm tra xem máy tính có gửi tham số "class" không
  if (!server.hasArg("class")) {
    server.send(400, "text/plain", "Loi: Thieu tham so class");
    return;
  }

  String classStr = server.arg("class");
  int class_id = classStr.toInt();

  long targetPosition = 0;
  
  if (class_id == 0) targetPosition = 0;                     // Chai nuoc
  else if (class_id == 1) targetPosition = steps90Degrees;   // Lon nuoc ngot
  else if (class_id == 2) targetPosition = steps90Degrees * 2; // Vo keo
  else if (class_id == 3) targetPosition = steps90Degrees * 3; // Thuoc la
  else {
    server.send(400, "text/plain", "Loi: Class khong hop le");
    return;
  }

  Serial.printf("\nNhan lenh phan loai Class %d qua Wi-Fi\n", class_id);

  // BƯỚC 1: Xoay Stepper
  stepper.moveTo(targetPosition);
  while (stepper.distanceToGo() != 0) {
    stepper.run();
    yield(); // Tránh lỗi Watchdog Timer khi vòng lặp chạy quá lâu
  }
  delay(500); 

  // BƯỚC 2: Servo mở ra
  myServo.write(SERVO_OPEN);
  delay(1000); 

  // BƯỚC 3: Đóng nắp
  digitalWrite(enPin, HIGH); 
  for (int angle = SERVO_OPEN; angle >= SERVO_START; angle -= 1) {
    myServo.write(angle);
    delay(12); 
  }
  delay(200); 
  digitalWrite(enPin, LOW); 

  Serial.println("Xu ly xong!");
  
  // Trả về kết quả 200 (OK) cho máy tính biết là đã xong
  server.send(200, "text/plain", "DONE");
}

void setup() {
  Serial.begin(115200);
  
  // --- KẾT NỐI WI-FI ---
  Serial.print("Dang ket noi Wi-Fi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nKet noi Wi-Fi thanh cong!");
  Serial.print("DIA CHI IP ESP32: ");
  Serial.println(WiFi.localIP()); // <-- QUAN TRỌNG: LẤY IP NÀY CHO PYTHON

  // --- CẤU HÌNH PHẦN CỨNG ---
  pinMode(enPin, OUTPUT);
  digitalWrite(enPin, LOW); 
  pinMode(hallPin, INPUT_PULLUP);

  ESP32PWM::allocateTimer(0);
  myServo.setPeriodHertz(50);
  myServo.attach(servoPin, 500, 2500); 
  myServo.write(SERVO_START); 

  stepper.setMaxSpeed(2000.0);
  stepper.setAcceleration(1000.0);
  
  // --- HOMING ---
  Serial.println("Dang tim diem goc (Homing)...");
  stepper.setSpeed(500); 
  while (digitalRead(hallPin) == HIGH) {
    stepper.runSpeed();
  }
  stepper.setCurrentPosition(0); 
  Serial.println("Da tim thay diem goc! San sang nhan lenh.");

  // --- CHẠY WEB SERVER ---
  server.on("/sort", HTTP_GET, handleSort); // Tạo đường dẫn API: http://IP_CUA_ESP/sort?class=X
  server.begin();
}

void loop() {
  // Lắng nghe các kết nối từ máy tính tới liên tục
  server.handleClient();
}