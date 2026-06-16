# Hệ thống Phân Loại Rác Tự Động (Smart Trash Classifier System)

Dự án Đồ án tốt nghiệp nghiên cứu, thiết kế và chế tạo hệ thống phân loại rác thông minh ứng dụng Thị giác máy tính (Computer Vision), Trí tuệ nhân tạo (YOLOv11m) và IoT. Hệ thống hoạt động theo kiến trúc 3 Node phân tán qua mạng Wi-Fi LAN.

---

## 📂 Cấu trúc thư mục dự án (Project Directory Structure)

Dự án được tổ chức khoa học thành các thư mục chuyên biệt:

```
SmartTrashClassifier/
├── README.md                           # Hướng dẫn chi tiết cài đặt và vận hành hệ thống
├── Documentation/                      # Tài liệu và báo cáo đồ án
│   ├── Graduation_Thesis.docx          # File báo cáo đồ án tốt nghiệp chi tiết
│   └── Images/                         # Tập hợp hình ảnh kết quả thực nghiệm, biểu đồ
├── Software_PC/                        # Phần mềm điều khiển trung tâm và xử lý AI trên PC
│   ├── run_pc_app.py                   # Code ứng dụng chính (CustomTkinter GUI + YOLO Object Tracking)
│   ├── config.json                     # File cấu hình kết nối, ngưỡng tin cậy AI, danh sách class rác
│   ├── stats.db                        # Cơ sở dữ liệu SQLite lưu lịch sử phân loại rác
│   └── system.log                      # Nhật ký hoạt động của phần mềm PC
├── Firmware/                           # Chương trình nạp cho các vi điều khiển ESP32
│   ├── Camera_Node/                    # Node ESP32-S3 Cam truyền dòng video MJPEG
│   │   ├── Camera_Node.ino             # File chương trình Arduino chính
│   │   ├── app_httpd.cpp               # Cấu hình truyền video stream qua HTTP
│   │   ├── camera_index.h              # Giao diện web cấu hình camera
│   │   ├── camera_pins.h               # Sơ đồ chân của module Camera ESP32-S3 EYE
│   │   └── partitions.csv              # Phân vùng bộ nhớ flash cho ESP32-S3
│   ├── Controller_Node/                # Node ESP32 điều khiển cơ cấu phân loại (Bản nâng cao v3.0)
│   │   └── Controller_Node.ino         # State Machine điều khiển động cơ bước, servo, và cổng API
│   └── Controller_Node_Simple/         # Node ESP32 điều khiển cơ cấu (Bản cơ bản v1.0 - Dự phòng)
│       └── Controller_Node_Simple.ino  # Code điều khiển cơ bản, hardcode cấu hình Wi-Fi
└── Hardware_PCB/                       # Thiết kế sơ đồ mạch điện và layout mạch in (KiCad)
    ├── THUNGRAC_AI_CAM.kicad_pcb       # Layout mạch in PCB (đã cấu hình đường dẫn 3D tương đối)
    ├── THUNGRAC_AI_CAM.kicad_sch       # Sơ đồ nguyên lý mạch điều khiển
    ├── THUNGRAC_AI_CAM.kicad_pro       # File quản lý project KiCad
    ├── THUNGRAC_AI_CAM.kicad_prl       # File thiết lập hiển thị cục bộ
    ├── THUNGRAC_AI_CAM.svg             # Bản vẽ sơ đồ mạch xuất dạng SVG
    ├── Library.pretty/                 # Thư viện footprint cục bộ của project
    ├── THUNGRAC_AI_CAM-backups/        # Thư mục sao lưu tự động của KiCad
    └── Libraries/                      # Thư viện 3D linh kiện dạng STEP/WRL (linh kiện ngoài)
        ├── ESP32-S3-DEVKITC-1U-N8R8/   # Thư viện footprint & 3D cho ESP32-S3 DevKit
        ├── LM2596-StepDown/            # Thư viện footprint & 3D cho mạch giảm áp buck LM2596
        └── TMC2209-Driver/             # Thư viện footprint & 3D cho driver TMC2209
```

---

## 💻 1. Phần mềm trung tâm trên PC (`Software_PC`)

Phần mềm viết bằng Python thực hiện các nhiệm vụ:
* Nhận stream video MJPEG từ `Camera_Node` qua Wi-Fi.
* Sử dụng mô hình **YOLOv11m** và bộ theo dõi vật thể (Object Tracking) để phát hiện rác trong khung hình.
* Khi phát hiện rác mới, phần mềm gửi lệnh HTTP Request `/sort?class=ID` tới `Controller_Node` để kích hoạt cơ cấu quay/cửa sập.
* Lưu lịch sử phân loại vào cơ sở dữ liệu **SQLite** (`stats.db`) và đồng bộ thời gian thực lên **Firebase Realtime Database**.

### Yêu cầu môi trường & Cài đặt:
1. Cài đặt Python (khuyên dùng bản **Python 3.10** hoặc **3.11**).
2. Di chuyển vào thư mục phần mềm:
   ```bash
   cd Software_PC
   ```
3. Cài đặt các thư viện cần thiết:
   ```bash
   pip install customtkinter opencv-python Pillow requests ultralytics
   ```
   *Lưu ý: Nếu bạn có card đồ họa NVIDIA, hãy cài đặt phiên bản PyTorch hỗ trợ CUDA để chạy AI mượt mà hơn.*

### Cấu hình hệ thống (`config.json`):
Trước khi chạy ứng dụng, hãy cấu hình các thông số trong file `config.json` cho phù hợp:
* `model_path`: Đường dẫn tới file mô hình YOLO (`.pt`).
* `confidence_threshold`: Ngưỡng độ tin cậy để nhận dạng rác (mặc định: `0.9`).
* `camera_stream_url`: Địa chỉ stream video của ESP32-S3 Cam (được tự động cập nhật qua UDP Discovery hoặc nhập thủ công).
* `esp32_controller_url`: Địa chỉ IP của ESP32 Controller điều khiển cơ cấu.
* `firebase_url`: URL Realtime Database của dự án Firebase để đồng bộ dữ liệu.

### Khởi chạy phần mềm:
```bash
python run_pc_app.py
```

---

## 📷 2. Node Camera (`Firmware/Camera_Node`)

Dành cho module **ESP32-S3 EYE** (hoặc board tích hợp cảm biến OV2640 tương đương).
* **Cơ chế hoạt động**: Stream dữ liệu ảnh MJPEG qua giao thức HTTP ở cổng `81` (`/stream`).
* **Tính năng Auto-Discovery**: Lắng nghe UDP Port `8888` để phản hồi địa chỉ IP cho PC tự động kết nối mà không cần cài đặt IP tĩnh.
* **Cấu hình Wi-Fi**: Nếu không kết nối được mạng Wi-Fi đã lưu, board sẽ tự phát một Access Point (AP) tên `SmartTrash-CAM` để bạn kết nối và nhập Wi-Fi thông qua giao diện WebPortal.

### Cách nạp code:
1. Mở file [Camera_Node.ino](file:///c:/Users/Namdr/Downloads/repo%20l%C3%AAn%20git%20v2/Firmware/Camera_Node/Camera_Node.ino) bằng phần mềm Arduino IDE.
2. Chọn board là **ESP32S3 Dev Module**.
3. Cấu hình các tham số nạp (Flash Size: 8MB/16MB, PSRAM: OPI PSRAM tùy theo board).
4. Nhấn Upload để nạp chương trình.

---

## ⚙️ 3. Node Điều Khiển Cơ Cấu (`Firmware/Controller_Node`)

Dành cho board **ESP32-S3** điều khiển trực tiếp phần cơ khí.
* **Cơ chế hoạt động**: Sử dụng mô hình **State Machine** để điều khiển luồng hoạt động phi tuần tự, không gây nghẽn Web Server:
  1. `STATE_IDLE`: Chờ lệnh phân loại từ PC.
  2. `STATE_SORT_MOVING_TO_BIN`: Xoay động cơ bước đưa khay chứa rác về góc rác tương ứng.
  3. `STATE_SORT_SERVO_OPENING`: Điều khiển Servo mở cửa sập để rác rơi xuống thùng.
  4. `STATE_SORT_SERVO_CLOSING`: Đóng cửa sập lại.
  5. `STATE_SORT_FINISHING`: Đưa động cơ bước về vị trí sẵn sàng và chuyển sang IDLE.
* **Homing tự động**: Tự động xoay động cơ bước tìm điểm gốc (vị trí nam châm quét qua cảm biến Hall) khi khởi động hoặc khi có yêu cầu cân chỉnh.

### Cách nạp code:
1. Mở file [Controller_Node.ino](file:///c:/Users/Namdr/Downloads/repo%20l%C3%AAn%20git%20v2/Firmware/Controller_Node/Controller_Node.ino) bằng Arduino IDE.
2. Cài đặt các thư viện phụ thuộc: `AccelStepper`, `ESP32Servo`.
3. Chọn board **ESP32S3 Dev Module** và cổng COM phù hợp rồi tiến hành nạp code.

---

## 🔌 4. Phần Thiết Kế Mạch (`Hardware_PCB`)

Dự án thiết kế sơ đồ nguyên lý mạch chính tích hợp vi điều khiển ESP32-S3, Driver TMC2209 điều khiển động cơ bước và cơ cấu Servo/Cảm biến Hall:
* Mạch nguồn sử dụng module Buck LM2596 để chuyển điện áp 12V từ pin/adapter về 5V cung cấp cho các vi điều khiển và Servo.
* **Tính di động của project**: Đường dẫn liên kết mô hình 3D (3D Models) của các linh kiện đã được chỉnh sửa về dạng tương đối sử dụng biến `${KIPRJMOD}/Libraries/...` thay vì đường dẫn tuyệt đối trên máy tính cũ. Điều này giúp các bạn có thể mở project KiCad trên bất cứ máy tính nào mà vẫn hiển thị đầy đủ linh kiện 3D trong 3D Viewer mà không bị lỗi thiếu file.
