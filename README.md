# Hệ thống Phân Loại Rác Tự Động (Smart Trash Classifier System)

Dự án Đồ án tốt nghiệp nghiên cứu, thiết kế và chế tạo hệ thống phân loại rác thông minh tích hợp Thị giác máy tính (Computer Vision), Trí tuệ nhân tạo (YOLOv11m) và Internet of Things (IoT). Hệ thống được triển khai trên kiến trúc phân tán gồm 3 Node kết nối qua mạng Wi-Fi mạng cục bộ (LAN).

---

## 📂 Cấu trúc thư mục dự án (Project Directory Structure)

Dự án được tổ chức một cách khoa học và tối ưu để quản lý cả phần mềm, firmware vi điều khiển, thiết kế phần cứng PCB và tài liệu báo cáo:

```
SmartTrashClassifier/
├── README.md                           # Hướng dẫn chi tiết cài đặt và vận hành hệ thống
├── Documentation/                      # Báo cáo thuyết minh và tài liệu thiết kế đồ án
│   ├── Graduation_Thesis.docx          # File báo cáo đồ án tốt nghiệp thuyết minh chi tiết
│   └── Images/                         # Tập hợp hình ảnh kết quả thực nghiệm, biểu đồ
├── Software_PC/                        # Phần mềm xử lý trung tâm và chạy AI trên máy tính
│   ├── run_pc_app.py                   # Script ứng dụng chính (CustomTkinter GUI + YOLO Object Tracking)
│   ├── config.json                     # File cấu hình kết nối, ngưỡng tin cậy AI, danh sách class rác
│   ├── stats.db                        # Cơ sở dữ liệu SQLite lưu lịch sử phân loại rác cục bộ
│   └── system.log                      # Nhật ký (log) ghi nhận lỗi và trạng thái hệ thống
├── Firmware/                           # Chương trình nạp cho các vi điều khiển ESP32
│   ├── Camera_Node/                    # Node ESP32-S3 Cam làm nhiệm vụ truyền dòng video MJPEG
│   │   ├── Camera_Node.ino             # File chương trình chính cho module camera
│   │   ├── app_httpd.cpp               # Cấu hình Web Server truyền hình ảnh chất lượng cao
│   │   ├── camera_index.h              # File chứa mã HTML cấu hình thông số camera
│   │   ├── camera_pins.h               # Định nghĩa sơ đồ chân camera ESP32-S3 EYE
│   │   └── partitions.csv              # Phân vùng bộ nhớ flash (nới rộng phân vùng app)
│   ├── Controller_Node/                # Node ESP32 điều khiển cơ cấu phân loại (Bản nâng cao v3.0)
│   │   └── Controller_Node.ino         # Máy trạng thái điều khiển động cơ bước, servo, và cổng API
│   └── Controller_Node_Simple/         # Node ESP32 điều khiển cơ cấu (Bản cơ bản v1.0 - Dự phòng)
│       └── Controller_Node_Simple.ino  # Code điều khiển cơ bản, kết nối Wi-Fi thủ công
└── Hardware_PCB/                       # Thiết kế sơ đồ nguyên lý và layout mạch in (KiCad)
    ├── THUNGRAC_AI_CAM.kicad_pcb       # Bản vẽ thiết kế mạch in PCB 
    ├── THUNGRAC_AI_CAM.kicad_sch       # Sơ đồ nguyên lý toàn mạch
    ├── THUNGRAC_AI_CAM.kicad_pro       # Quản lý cấu hình dự án KiCad
    ├── THUNGRAC_AI_CAM.kicad_prl       # File lưu trữ cài đặt hiển thị cục bộ
    ├── THUNGRAC_AI_CAM.svg             # Sơ đồ mạch điện xuất ra định dạng ảnh vector
    ├── Library.pretty/                 # Tập hợp footprint linh kiện nội bộ của mạch
    ├── THUNGRAC_AI_CAM-backups/        # Thư mục chứa các file sao lưu tự động của dự án
    └── Libraries/                      # Thư viện mô hình 3D (STEP/WRL) của các linh kiện bên ngoài
        ├── ESP32-S3-DEVKITC-1U-N8R8/   # Thư viện footprint & 3D cho ESP32-S3 DevKit
        ├── LM2596-StepDown/            # Thư viện footprint & 3D cho mạch giảm áp LM2596
        └── TMC2209-Driver/             # Thư viện footprint & 3D cho module Driver TMC2209
```

---

## 🛠️ Sơ đồ Kiến trúc & Luồng hoạt động (System Architecture & Dataflow)

Hệ thống hoạt động theo mô hình luồng khép kín thời gian thực:
1. **Thu thập dữ liệu hình ảnh (Camera Node)**: Module ESP32-S3 Cam thu nhận hình ảnh từ camera OV2640 và truyền phát liên tục dưới dạng luồng MJPEG Stream qua giao thức HTTP ở cổng `81`.
2. **Xử lý trí tuệ nhân tạo (Central PC Node)**: 
   * Máy tính PC kết nối vào luồng stream, giải mã từng khung hình.
   * Áp dụng mô hình **YOLOv11m** được tối ưu hóa để định vị các loại rác thải.
   * Bộ theo dõi đối tượng (**Object Tracking**) gán ID duy nhất cho mỗi vật thể để tránh phát hiện lặp lại.
   * Khi xác định loại rác vượt qua ngưỡng tin cậy (Confidence Threshold), PC gửi một yêu cầu GET HTTP đến `Controller_Node` qua API: `http://<CONTROLLER_IP>/sort?class=<CLASS_ID>`.
   * Ghi nhận lịch sử phân loại vào cơ sở dữ liệu **SQLite** cục bộ và đồng bộ lên **Firebase Cloud**.
3. **Thực thi phân loại (Controller Node)**:
   * Nhận lệnh từ PC, chuyển sang trạng thái phân loại tương ứng.
   * Xoay khay động cơ bước đến vị trí thùng rác tương ứng.
   * Kích hoạt Servo mở cửa sập để giải phóng rác, sau đó đóng cửa và quay lại vị trí ban đầu.

---

## 🔌 1. Sơ đồ kết nối phần cứng và Pinout (`Controller_Node`)

Mạch PCB chính liên kết Node điều khiển với các linh kiện chấp hành. Dưới đây là bảng định nghĩa chân kết nối trên vi điều khiển **ESP32-S3**:

| Linh kiện chấp hành | Chân trên ESP32-S3 | Chức năng chi tiết |
| :--- | :---: | :--- |
| **Servo Motor** (Nắp cửa sập) | `GPIO 4` | Điều chế độ rộng xung (PWM) góc mở từ $105^\circ$ đến $170^\circ$. |
| **Driver Step TMC2209** (Step Pin) | `GPIO 5` | Tạo xung nhịp bước động cơ bước (NEMA 17). |
| **Driver Step TMC2209** (Dir Pin) | `GPIO 6` | Xác định chiều quay động cơ (Thuận/Nghịch). |
| **Driver Step TMC2209** (En Pin) | `GPIO 7` | Cho phép/Vô hiệu hóa driver động cơ (Tiết kiệm điện khi rảnh). |
| **Cảm biến Hall A3144** | `GPIO 15` | Cảm biến từ trường từ nam châm để xác định vị trí góc 0 (Homing). |
| **Đèn LED báo trạng thái** | `GPIO 2` | Nhấp nháy báo hiệu kết nối Wi-Fi hoặc trạng thái máy trạng thái. |

---

## 🧠 2. Máy trạng thái Node điều khiển (`Controller_Node`)

Node điều khiển cơ cấu phân loại được lập trình theo mô hình **Finit State Machine (FSM)** bất đồng bộ, giúp vi điều khiển vẫn xử lý Web Server mượt mà khi động cơ đang quay:

* **`STATE_IDLE`**: Trạng thái nghỉ, liên tục lắng nghe yêu cầu API `/sort` từ PC.
* **`STATE_HOMING`**: Trạng thái tìm điểm gốc. Động cơ bước quay chậm cho đến khi cảm biến Hall phát hiện nam châm tại khay mặc định (Góc 0).
* **`STATE_SORT_MOVING_TO_BIN`**: Xoay động cơ bước một góc tương ứng với nhãn rác nhận được:
  * *Class 0 (Chai nước)*: Quay về góc $0^\circ$ (Vị trí gốc).
  * *Class 1 (Lon nước ngọt)*: Quay về góc $90^\circ$.
  * *Class 2 (Thuốc lá)*: Quay về góc $180^\circ$.
  * *Class 3 (Vỏ kẹo)*: Quay về góc $270^\circ$.
* **`STATE_SORT_SERVO_OPENING`**: Kích hoạt Servo kéo cửa sập để mở khay chứa, cho rác rơi xuống thùng.
* **`STATE_SORT_SERVO_CLOSING`**: Servo quay ngược trở lại để đóng nắp cửa sập an toàn.
* **`STATE_SORT_FINISHING`**: Vô hiệu hóa lực giữ động cơ bước (Disable Stepper) để bảo vệ Driver khỏi bị nóng, đồng thời reset trạng thái về `STATE_IDLE`.

---

## 💻 3. Phần mềm điều khiển trung tâm trên PC (`Software_PC`)

### Thiết lập môi trường Python:
1. Đảm bảo máy tính của bạn đã được cài đặt Python 3.10 trở lên.
2. Di chuyển vào thư mục ứng dụng:
   ```bash
   cd Software_PC
   ```
3. Cài đặt các gói thư viện cần thiết:
   ```bash
   pip install customtkinter opencv-python Pillow requests ultralytics
   ```

### Giao thức Tự động dò tìm thiết bị (UDP Auto-Discovery):
Để thuận tiện khi sử dụng trong môi trường mạng Wi-Fi động (IP thay đổi liên tục), phần mềm PC tích hợp cơ chế tự động tìm kiếm IP của các Node ESP32:
* PC phát (Broadcast) định kỳ chuỗi gói tin `"WHO_IS_TRASH_CTRL"` qua giao thức UDP ở port `8888`.
* Các node ESP32 khi nhận được gói tin này sẽ phản hồi lại chuỗi `"I_AM_TRASH_CTRL|<IP_CỦA_ESP>"`.
* Giao diện PC sẽ tự động bắt lấy IP này và cập nhật vào chương trình chính mà không cần người dùng phải cấu hình IP tĩnh thủ công.

### Chạy ứng dụng:
```bash
python run_pc_app.py
```
* **AI Slider**: Cho phép tinh chỉnh trực tiếp ngưỡng tin cậy nhận diện trên giao diện.
* **Auto Tracking Mode**: Bật tính năng theo dõi vật thể bằng thuật toán tích hợp để tránh gửi trùng lệnh khi vật thể chưa đi qua hết tầm camera.

---

## 🔌 4. Thiết kế mạch PCB (`Hardware_PCB`)

Mạch thiết kế hoàn chỉnh trên phần mềm **KiCad** hỗ trợ nạp chương trình, lọc nhiễu cho động cơ công suất lớn và bảo vệ vi điều khiển:
* Sử dụng nguồn đầu vào 12V (Pin LiPo 3S hoặc Adapter) hạ áp qua Buck LM2596 để cấp dòng 5V ổn định cho hệ thống điều khiển.
* Tích hợp tụ điện chống sụt áp tức thời khi động cơ bước khởi động làm treo ESP32.
* **Tính di động của project**: Các liên kết mô hình 3D linh kiện đã được chuyển sang đường dẫn tương đối sử dụng biến môi trường `${KIPRJMOD}/Libraries/...` thay vì đường dẫn tuyệt đối tĩnh trên ổ đĩa. Nhờ vậy, khi bạn tải thư mục dự án này về bất kỳ máy tính nào khác và mở bằng KiCad, tất cả mô hình linh kiện 3D vẫn sẽ hiển thị chính xác và đầy đủ trong 3D Viewer mà không bị báo lỗi thiếu file 3D.
