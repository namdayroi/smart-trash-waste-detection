import customtkinter as ctk
import cv2
import threading
import time
import json
import requests
import logging
import os
import sys
import sqlite3
from datetime import datetime
from PIL import Image
from tkinter import filedialog
from ultralytics import YOLO
from collections import defaultdict
from queue import Queue, Empty
import socket

class Config:
    DEFAULTS = {
        "model_path": "C:/Users/Namdr/Downloads/best.pt",
        "confidence_threshold": 0.8,
        "camera_stream_url": "http://192.168.1.4:8080",
        "esp32_controller_url": "http://192.168.151.229",
        "class_names": ["Chai nước", "Lon nước ngọt", "Thuốc lá", "Vỏ kẹo"],
        "request_timeout": 15,
        "auto_detect": True,
        "health_check_interval": 10,
        "firebase_url": "",
    }

    def __init__(self, path=None):
        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.json")
        self.path = path
        self.data = self.DEFAULTS.copy()
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
        except Exception as e:
            logging.warning(f"Config load error: {e}")

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Config save error: {e}")

    def __getitem__(self, key):
        return self.data.get(key, self.DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value

class Theme:
    BG_DARK       = "#f7fee7"  # Softest Lime
    BG_CARD       = "#ffffff"  # Pure White
    BG_INPUT      = "#fafff0"  # Very light lime
    BG_HOVER      = "#ecfccb"
    PRIMARY       = "#064e3b"  # Deep Forest Green
    ACCENT        = "#22c55e"  # Emerald Green
    SUCCESS       = "#16a34a"  # Green 600
    WARNING       = "#d97706"  # Amber 500
    DANGER        = "#dc2626"  # Red 600
    INFO          = "#10b981"  # Teal
    TEXT          = "#064e3b"  # Deep Forest
    TEXT_DIM      = "#14532d"  # Dark Green
    TEXT_MUTED    = "#65a30d"  # Lime 600
    HEADER_BG     = "#4ade80"  # Light Lime Green (Requested)
    HEADER_TEXT   = "#064e3b"  # Deep Forest
    BORDER        = "#dcfce7"  # Pale Green
    CLASS_COLORS  = ["#16a34a", "#dc2626", "#d97706", "#8b5cf6"]
    CLASS_ICONS   = ["", "", "", ""]
    TITLE         = ("Segoe UI", 24, "bold")
    HEADING       = ("Segoe UI", 17, "bold")
    BODY          = ("Segoe UI", 15)
    SMALL         = ("Segoe UI", 13)
    MONO          = ("Consolas", 13)
    BIG_NUM       = ("Segoe UI", 34, "bold")

class ESP32Controller:
    def __init__(self, base_url: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth = ("admin", "SmartTrash2026")
        self.connected = False
        self.last_response_time = 0.0

    def check_health(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/status", auth=self.auth, timeout=3)
            self.connected = r.status_code == 200
        except Exception:
            self.connected = False
        return self.connected

    def send_sort(self, class_id: int) -> dict:
        try:
            t0 = time.time()
            r = requests.get(
                f"{self.base_url}/sort",
                params={"class": class_id},
                auth=self.auth,
                timeout=self.timeout,
            )
            self.last_response_time = time.time() - t0
            if r.status_code in [200, 202]: # Hỗ trợ Non-blocking 202 Accepted
                try:
                    return r.json()
                except ValueError:
                    return {"status": "ok", "message": r.text}
            return {"status": "error", "message": f"HTTP {r.status_code}"}
        except requests.exceptions.Timeout:
            return {"status": "error", "message": "Timeout - ESP32 không phản hồi"}
        except requests.exceptions.ConnectionError:
            self.connected = False
            return {"status": "error", "message": "Mất kết nối ESP32"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

class VideoStream:
    def __init__(self, url: str):
        self.url = url
        if "?" not in self.url and "http" in self.url:
            self.url += "?token=SmartTrash2026"
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self.connected = False
        self.fps = 0.0

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        fc, ft = 0, time.time()
        reconnect_wait = 1
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                self.connected = False
                try:
                    self._cap = cv2.VideoCapture(self.url)
                    if self._cap.isOpened():
                        self.connected = True
                        reconnect_wait = 1
                    else:
                        time.sleep(reconnect_wait)
                        reconnect_wait = min(reconnect_wait * 2, 10)
                        continue
                except Exception:
                    time.sleep(reconnect_wait)
                    reconnect_wait = min(reconnect_wait * 2, 10)
                    continue

            ret, frame = self._cap.read()
            if not ret:
                self.connected = False
                self._cap = None
                continue

            with self._lock:
                self._frame = frame

            fc += 1
            elapsed = time.time() - ft
            if elapsed >= 1.0:
                self.fps = fc / elapsed
                fc, ft = 0, time.time()

    def get_frame(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self):
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None

class TrashClassifierApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title(" Hệ Thống Phân Loại Rác Thông Minh v5.0")
        self.geometry("1440x900")
        self.minsize(1100, 720)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=Theme.BG_DARK)

        self.cfg = Config()
        self._setup_logging()
        self.video = VideoStream(self.cfg["camera_stream_url"])
        self.esp32 = ESP32Controller(self.cfg["esp32_controller_url"], self.cfg["request_timeout"])

        self.is_running = False
        self.model = None
        self.stats = defaultdict(int)
        self.total = 0
        self.start_time = None
        self._cam_was_connected = False
        self._log_q: Queue = Queue()
        self._http_queue: Queue = Queue() 
        self.tracked_ids = set() 

       
        self._setup_db()

        self._build_header()
        self._build_main()
        self._build_status_bar()

        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50,   self._tick_frame)
        self.after(5000, self._tick_health)
        self.after(100,  self._tick_log)

    
        self._log("Hệ thống v4.0 khởi động (Auto-Discovery)...", Theme.INFO)
        self._run_auto_discovery()
        self.after(300, self._load_model)

    
    def _run_auto_discovery(self):
        def _scan():
            self._log("", "Khởi động Radar Quét IP Tự Động (UDP 8888)...", Theme.INFO)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(3.0)
            
            found_cam = False
            found_ctrl = False
            
            try:
                # Gửi gói tin quét
                sock.sendto(b"WHO_IS_TRASH_CAM", ("255.255.255.255", 8888))
                sock.sendto(b"WHO_IS_TRASH_CTRL", ("255.255.255.255", 8888))
                
                start_t = time.time()
                while time.time() - start_t < 3.0 and not (found_cam and found_ctrl):
                    try:
                        data, _ = sock.recvfrom(1024)
                        msg = data.decode("utf-8")
                        if msg.startswith("I_AM_TRASH_CAM|"):
                            ip = msg.split("|")[1]
                            new_url = f"http://{ip}:81/stream"
                            self.cfg["camera_stream_url"] = new_url
                            self.video.url = new_url + "?token=SmartTrash2026"
                            self.cfg.save()
                            self._log("", f"Đã tự động tìm thấy Camera tại {ip}", Theme.SUCCESS)
                            found_cam = True
                        elif msg.startswith("I_AM_TRASH_CTRL|"):
                            ip = msg.split("|")[1]
                            new_url = f"http://{ip}"
                            self.cfg["esp32_controller_url"] = new_url
                            self.esp32.base_url = new_url
                            self.cfg.save()
                            self._log("", f"Đã tự động tìm thấy Điều khiển tại {ip}", Theme.SUCCESS)
                            found_ctrl = True
                    except socket.timeout:
                        break
            except Exception as e:
                self._log("", f"Lỗi quét UDP: {e}", Theme.DANGER)
            finally:
                sock.close()
                
            if not found_cam and not found_ctrl:
                self._log("", "Không tìm thiết bị mới nào, dùng IP cũ.", Theme.WARNING)
                
        threading.Thread(target=_scan, daemon=True).start()

    def _setup_db(self):
        db_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "stats.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS sort_log 
                               (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                                class_id INTEGER, class_name TEXT, 
                                conf REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        self.conn.commit()
        
        try:
            self.cursor.execute("SELECT class_id, COUNT(*) FROM sort_log GROUP BY class_id")
            for row in self.cursor.fetchall():
                self.stats[row[0]] = row[1]
                self.total += row[1]
            self.after(1000, self._refresh_stats)
        except Exception as e:
            self._log("", f"Lỗi đọc DB: {e}", Theme.DANGER)

    def _setup_logging(self):
        log_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "system.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
        )

    def _log(self, icon: str, msg: str, color: str = Theme.TEXT_DIM):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_q.put(f"[{ts}] {icon} {msg}")
        logging.info(msg)

    def _tick_log(self):
        try:
            while True:
                line = self._log_q.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", line + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except Empty:
            pass
        self.after(80, self._tick_log)

    def _build_header(self):
        # Header chính - nền xanh navy chuyên nghiệp
        hdr = ctk.CTkFrame(self, fg_color=Theme.HEADER_BG, height=70, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        # Logo + Tên hệ thống
        left = ctk.CTkFrame(hdr, fg_color="transparent")
        left.pack(side="left", padx=20, pady=8)
        ctk.CTkLabel(left, text="  HỆ THỐNG PHÂN LOẠI RÁC THÔNG MINH",
                     font=Theme.TITLE, text_color=Theme.HEADER_TEXT).pack(anchor="w")
        ctk.CTkLabel(left, text="Smart Trash Classification System  •  AI Engine: YOLO11m  •  v5.0",
                     font=("Segoe UI", 11), text_color="#166534").pack(anchor="w")

        # Trạng thái kết nối bên phải
        dot_fr = ctk.CTkFrame(hdr, fg_color="#bbf7d0", corner_radius=8)
        dot_fr.pack(side="right", padx=20, pady=14)
        ctk.CTkLabel(dot_fr, text="ESP32-CAM:", font=("Segoe UI", 13), text_color="#166534").grid(row=0, column=0, padx=(10,4), pady=4)
        self.dot_cam = ctk.CTkLabel(dot_fr, text="●", font=("Segoe UI", 18), text_color="#ef4444")
        self.dot_cam.grid(row=0, column=1, padx=(0,4))
        self.lbl_cam = ctk.CTkLabel(dot_fr, text="Offline", font=("Segoe UI", 13, "bold"), text_color="#ef4444")
        self.lbl_cam.grid(row=0, column=2, padx=(0,14))
        ctk.CTkLabel(dot_fr, text="Controller:", font=("Segoe UI", 13), text_color="#166534").grid(row=0, column=3, padx=(0,4))
        self.dot_esp = ctk.CTkLabel(dot_fr, text="●", font=("Segoe UI", 18), text_color="#ef4444")
        self.dot_esp.grid(row=0, column=4, padx=(0,4))
        self.lbl_esp = ctk.CTkLabel(dot_fr, text="Offline", font=("Segoe UI", 13, "bold"), text_color="#ef4444")
        self.lbl_esp.grid(row=0, column=5, padx=(0,10))

        # Panel thành viên nhóm - nền xanh nhạt bên dưới header
        team = ctk.CTkFrame(self, fg_color="#ecfccb", height=36, corner_radius=0)
        team.pack(fill="x"); team.pack_propagate(False)
        team_txt = (
            "📚 Nhóm thực hiện:  "
            "1. Nguyễn Văn Nam  (MSSV: 2022605582)     "
            "2. Đinh Huy Mạnh  (MSSV: 2022605768)     "
            "3. Nguyễn Đức Văn  (MSSV: 2022602436)     "
            "-  Lớp: 2022DHRBNT01  •  Khóa 17"
        )
        ctk.CTkLabel(team, text=team_txt, font=("Segoe UI", 14, "bold"),
                     text_color="#1e40af").pack(side="left", padx=20, pady=6)

    def _build_main(self):
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        wrap.grid_columnconfigure(0, weight=7) # Camera & Log
        wrap.grid_columnconfigure(1, weight=3) # Sidebar (Full height)
        wrap.grid_rowconfigure(0, weight=1)    # Camera row
        wrap.grid_rowconfigure(1, weight=0)    # Log row (fixed-ish)

        self._build_video_card(wrap)
        self._build_log_panel(wrap)
        self._build_sidebar(wrap)

    def _build_video_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=Theme.BORDER)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        top = ctk.CTkFrame(card, fg_color="#eff6ff", height=42, corner_radius=0)
        top.pack(fill="x", padx=0, pady=(0, 4)); top.pack_propagate(False)
        ctk.CTkLabel(top, text="📹  CAMERA TRỰC TIẾP", font=Theme.HEADING,
                     text_color=Theme.PRIMARY).pack(side="left", padx=14)
        self.lbl_fps = ctk.CTkLabel(top, text="FPS: --", font=("Segoe UI", 13, "bold"),
                                    text_color=Theme.SUCCESS)
        self.lbl_fps.pack(side="right", padx=14)
        self._video_frame = ctk.CTkFrame(card, fg_color="#f8fafc", corner_radius=6)
        self._video_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._video_frame.pack_propagate(False)

        self.lbl_video = ctk.CTkLabel(self._video_frame,
                                      text="Nhấn  ▶ BẮT ĐẦU  để khởi chạy hệ thống",
                                      font=("Segoe UI", 20), text_color=Theme.TEXT_MUTED,
                                      fg_color="transparent")
        self.lbl_video.pack(fill="both", expand=True)

    def _build_sidebar(self, parent):
        sb = ctk.CTkScrollableFrame(parent, fg_color="transparent", width=380)
        sb.grid(row=0, column=1, rowspan=2, sticky="nsew")

        self._card_model(sb)      
        self._card_connection(sb)
        self._card_detection(sb)
        self._card_stats(sb)
        self._card_controls(sb)

    def _card_model(self, p):
        c = ctk.CTkFrame(p, fg_color=Theme.BG_CARD, corner_radius=12,
                         border_width=1, border_color=Theme.BORDER)
        c.pack(fill="x", pady=(0, 6))
        
        ctk.CTkLabel(c, text="🧠 AI MODEL", font=Theme.HEADING,
                     text_color=Theme.ACCENT, anchor="w").pack(fill="x", padx=12, pady=(8, 2))
        
        mf = ctk.CTkFrame(c, fg_color=Theme.BG_INPUT, corner_radius=8)
        mf.pack(fill="x", padx=12, pady=(2, 10))
        
        icon_lbl = ctk.CTkLabel(mf, text="📂", font=("Segoe UI", 14))
        icon_lbl.pack(side="left", padx=(8, 2))
        
        model_name = os.path.basename(self.cfg["model_path"])
        self.lbl_model_name = ctk.CTkLabel(mf, text=model_name, font=("Segoe UI", 13, "bold"), text_color=Theme.TEXT)
        self.lbl_model_name.pack(side="left", padx=2, fill="x", expand=True)
        
        self.btn_mdl = ctk.CTkButton(mf, text="Chọn", width=60, height=26, font=("Segoe UI", 13, "bold"),
                                      fg_color=Theme.ACCENT, hover_color="#2563eb", command=self._select_model)
        self.btn_mdl.pack(side="right", padx=6, pady=6)

    def _card_connection(self, p):
        c = ctk.CTkFrame(p, fg_color=Theme.BG_CARD, corner_radius=10,
                         border_width=1, border_color=Theme.BORDER)
        c.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(c, text="  TRẠNG THÁI KẾT NỐI", font=Theme.HEADING,
                     text_color=Theme.PRIMARY, anchor="w").pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkFrame(c, fg_color=Theme.BORDER, height=1).pack(fill="x", padx=14, pady=(0,8))

    def _card_detection(self, p):
        c = ctk.CTkFrame(p, fg_color=Theme.BG_CARD, corner_radius=12,
                         border_width=1, border_color=Theme.BORDER)
        c.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(c, text="  NHẬN DIỆN", font=Theme.HEADING,
                     text_color=Theme.ACCENT, anchor="w").pack(fill="x", padx=12, pady=(8, 2))

        self.lbl_det_name = ctk.CTkLabel(c, text="- Chờ vật thể -",
                                          font=("Segoe UI", 22, "bold"), text_color=Theme.TEXT_MUTED)
        self.lbl_det_name.pack(padx=12, pady=2)

        cf = ctk.CTkFrame(c, fg_color="transparent"); cf.pack(fill="x", padx=12, pady=0)
        ctk.CTkLabel(cf, text="Độ tin cậy:", font=Theme.SMALL, text_color=Theme.TEXT_DIM).pack(side="left")
        self.lbl_conf = ctk.CTkLabel(cf, text="---", font=("Segoe UI", 12, "bold"), text_color=Theme.ACCENT)
        self.lbl_conf.pack(side="right")

        self.bar_conf = ctk.CTkProgressBar(c, height=8, corner_radius=4,
                                            fg_color=Theme.BG_INPUT, progress_color=Theme.ACCENT)
        self.bar_conf.pack(fill="x", padx=12, pady=(2, 4)); self.bar_conf.set(0)

        self.lbl_det_status = ctk.CTkLabel(c, text="Đang chờ...", font=("Segoe UI", 10),
                                            text_color=Theme.TEXT_MUTED)
        self.lbl_det_status.pack(padx=12, pady=(0, 6))

    def _card_stats(self, p):
        c = ctk.CTkFrame(p, fg_color=Theme.BG_CARD, corner_radius=12,
                         border_width=1, border_color=Theme.BORDER)
        c.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(c, text=" THỐNG KÊ", font=Theme.HEADING,
                     text_color=Theme.ACCENT, anchor="w").pack(fill="x", padx=12, pady=(8, 4))

        # GRID 2x2 để tiết kiệm chiều cao
        g = ctk.CTkFrame(c, fg_color="transparent")
        g.pack(fill="x", padx=8, pady=(0, 4))
        g.grid_columnconfigure((0, 1), weight=1)

        names = self.cfg["class_names"]
        self._stat_lbls = []; self._stat_bars = []
        for i, name in enumerate(names):
            color = Theme.CLASS_COLORS[i] if i < len(Theme.CLASS_COLORS) else Theme.ACCENT
            icon  = Theme.CLASS_ICONS[i]  if i < len(Theme.CLASS_ICONS) else "?"
            
            item = ctk.CTkFrame(g, fg_color=Theme.BG_INPUT, corner_radius=8)
            item.grid(row=i//2, column=i%2, padx=4, pady=4, sticky="nsew")
            
            ctk.CTkLabel(item, text=f"{icon} {name}", font=("Segoe UI", 16, "bold"), text_color=Theme.TEXT).pack(pady=(6, 0))
            lbl = ctk.CTkLabel(item, text="0", font=("Segoe UI", 24, "bold"), text_color=color)
            lbl.pack(pady=(0, 6))
            self._stat_lbls.append(lbl)
            
            # Progress bar mini nằm dưới item
            bar = ctk.CTkProgressBar(item, height=4, corner_radius=2, fg_color="#e2e8f0", progress_color=color)
            bar.pack(fill="x", padx=8, pady=(0, 6)); bar.set(0)
            self._stat_bars.append(bar)

        tr = ctk.CTkFrame(c, fg_color=Theme.BG_INPUT, corner_radius=8)
        tr.pack(fill="x", padx=12, pady=(4, 8))
        ctk.CTkLabel(tr, text="Tổng cộng:", font=("Segoe UI", 14, "bold"), text_color=Theme.TEXT).pack(side="left", padx=10, pady=6)
        
        self.btn_reset = ctk.CTkButton(tr, text="Đặt lại", font=("Segoe UI", 12, "bold"), width=70, 
                                        fg_color=Theme.WARNING, hover_color="#b45309", command=self._reset_stats)
        self.btn_reset.pack(side="right", padx=10)
        
        self.lbl_total = ctk.CTkLabel(tr, text="0", font=("Segoe UI", 26, "bold"), text_color=Theme.ACCENT)
        self.lbl_total.pack(side="right", padx=(10, 5))

    def _card_controls(self, p):
        c = ctk.CTkFrame(p, fg_color=Theme.BG_CARD, corner_radius=12,
                         border_width=1, border_color=Theme.BORDER)
        c.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(c, text=" BẢNG ĐIỀU KHIỂN", font=Theme.HEADING,
                     text_color=Theme.ACCENT, anchor="w").pack(fill="x", padx=12, pady=(8, 4))

        bf = ctk.CTkFrame(c, fg_color="transparent"); bf.pack(fill="x", padx=12, pady=2)
        self.btn_start = ctk.CTkButton(bf, text="BẮT ĐẦU", font=("Segoe UI", 15, "bold"),
                                        fg_color=Theme.SUCCESS, hover_color="#059669",
                                        height=44, corner_radius=8, command=self._start)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=(0, 3))
        self.btn_stop = ctk.CTkButton(bf, text="DỪNG", font=("Segoe UI", 15, "bold"),
                                       fg_color=Theme.DANGER, hover_color="#e11d48",
                                       height=44, corner_radius=8, state="disabled", command=self._stop)
        self.btn_stop.pack(side="right", expand=True, fill="x", padx=(3, 0))

        sf = ctk.CTkFrame(c, fg_color="transparent"); sf.pack(fill="x", padx=12, pady=(6, 0))
        ctk.CTkLabel(sf, text="Ngưỡng AI:", font=Theme.SMALL, text_color=Theme.TEXT_DIM).pack(side="left")
        self.lbl_thr = ctk.CTkLabel(sf, text=f"{self.cfg['confidence_threshold']:.0%}",
                                     font=("Segoe UI", 12, "bold"), text_color=Theme.ACCENT)
        self.lbl_thr.pack(side="right")
        self.slider = ctk.CTkSlider(c, from_=0.3, to=0.95, number_of_steps=65,
                                     fg_color="#e2e8f0", progress_color=Theme.ACCENT,
                                     button_color=Theme.ACCENT, button_hover_color="#2563eb",
                                     command=self._on_slider)
        self.slider.pack(fill="x", padx=12, pady=(0, 4)); self.slider.set(self.cfg["confidence_threshold"])

        self.var_auto = ctk.BooleanVar(value=self.cfg["auto_detect"])
        ctk.CTkSwitch(c, text="  Auto Tracking Mode", font=("Segoe UI", 13),
                       text_color=Theme.TEXT_DIM, variable=self.var_auto,
                       fg_color="#e2e8f0", progress_color=Theme.SUCCESS,
                       button_color="#ffffff").pack(padx=12, pady=(2, 10), anchor="w")

    def _build_log_panel(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD, corner_radius=10,
                              border_width=1, border_color=Theme.BORDER, height=120)
        frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))
        frame.pack_propagate(False)

        top = ctk.CTkFrame(frame, fg_color="#eff6ff", height=36, corner_radius=0)
        top.pack(fill="x", padx=0, pady=(0, 4)); top.pack_propagate(False)
        ctk.CTkLabel(top, text=" NHẬT KÝ HỆ THỐNG", font=Theme.HEADING,
                     text_color=Theme.PRIMARY).pack(side="left", padx=14)
        ctk.CTkButton(top, text="Xóa log", width=90, height=26, font=Theme.SMALL,
                       fg_color=Theme.DANGER, hover_color="#b91c1c", text_color="white",
                       command=self._clear_log).pack(side="right", padx=10, pady=5)

        self.log_box = ctk.CTkTextbox(frame, font=Theme.MONO, fg_color="#f8fafc",
                                       text_color=Theme.TEXT, corner_radius=6)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal"); self.log_box.delete("1.0", "end"); self.log_box.configure(state="disabled")

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, fg_color=Theme.HEADER_BG, height=32, corner_radius=0)
        bar.pack(fill="x", side="bottom"); bar.pack_propagate(False)
        self.sb_fps = ctk.CTkLabel(bar, text="FPS: --", font=("Segoe UI", 12),
                                    text_color="#93c5fd"); self.sb_fps.pack(side="left", padx=14)
        ctk.CTkLabel(bar, text="│", text_color="#475569").pack(side="left")
        self.sb_up = ctk.CTkLabel(bar, text="Uptime: 00:00:00", font=("Segoe UI", 12),
                                   text_color="#93c5fd"); self.sb_up.pack(side="left", padx=14)
        ctk.CTkLabel(bar, text="│", text_color="#475569").pack(side="left")
        self.sb_model = ctk.CTkLabel(bar, text="Model: đang tải...", font=("Segoe UI", 12),
                                      text_color="#93c5fd"); self.sb_model.pack(side="left", padx=14)
        self.sb_state = ctk.CTkLabel(bar, text="Stopped", font=("Segoe UI", 12, "bold"),
                                      text_color=Theme.WARNING); self.sb_state.pack(side="right", padx=14)

    def _select_model(self):
        file_path = filedialog.askopenfilename(
            title="Chọn file Model YOLO",
            filetypes=[("YOLO Model", "*.pt"), ("All files", "*.*")]
        )
        if file_path:
            self.cfg["model_path"] = file_path
            self.cfg.save()
            self.lbl_model_name.configure(text=os.path.basename(file_path))
            self._log(" ", f"Đã chọn model mới: {os.path.basename(file_path)}", Theme.INFO)
            self._load_model()

    def _load_model(self):
        def _do():
            try:
                p = self.cfg["model_path"]
                self.model = YOLO(p)
                # Chẩn đoán: In mapping ra log để kiểm tra triệt để
                m_names = self.model.names
                diag = ", ".join([f"{k}:{v}" for k,v in m_names.items()])
                self._log( f"Model Ready! Mapping AI: {diag}", Theme.SUCCESS)
                self.after(0, lambda: self.sb_model.configure(text=f"Model: {os.path.basename(p)}"))
            except Exception as e:
                self._log("", f"Lỗi tải model: {e}", Theme.DANGER)
                self.after(0, lambda: self.sb_model.configure(text="Model: Error ", text_color=Theme.DANGER))
        threading.Thread(target=_do, daemon=True).start()

    def _start(self):
        if self.model is None:
            self._log("", "Model chưa sẵn sàng!", Theme.DANGER)
            return
        self.is_running = True
        self.start_time = datetime.now()
        self.video = VideoStream(self.cfg["camera_stream_url"])
        self.video.start()
        self._log( "Đang kết nối camera...", Theme.INFO)

        threading.Thread(target=self._do_health_check, daemon=True).start()
        threading.Thread(target=self._detection_loop, daemon=True).start()
        threading.Thread(target=self._http_worker, daemon=True).start()

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.sb_state.configure(text="Running", text_color=Theme.SUCCESS)
        self._log("", "Hệ thống v5.0 đã khởi động!", Theme.SUCCESS)

    def _stop(self):
        self.is_running = False
        self.video.stop()
        self._cam_was_connected = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.sb_state.configure(text="Stopped", text_color=Theme.WARNING)
        self.lbl_video.configure(image=None, text="Camera đã dừng")
        self.dot_cam.configure(text_color=Theme.DANGER)
        self.lbl_cam.configure(text="Ngắt kết nối", text_color=Theme.DANGER)
        self._log("", "Hệ thống đã dừng.", Theme.INFO)

    def _detection_loop(self):
        """Sử dụng Tracking để tránh gửi lệnh trùng lặp cho cùng 1 vật thể."""
        self._det_frame = None
        self._det_frame_lock = threading.Lock()
        self.tracked_ids = set() # Reset danh sách ID khi start

        while self.is_running:
            frame = self.video.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            annotated = frame.copy()
            should_detect = self.var_auto.get() and self.model is not None

            if should_detect:
                try:
                    thr = self.slider.get()
                    # Sử dụng Tracker tích hợp của YOLO
                    results = self.model.track(frame, persist=True, conf=thr, verbose=False)
                    annotated = results[0].plot()

                    if results[0].boxes.id is not None:
                        boxes = results[0].boxes
                        for i in range(len(boxes)):
                            box_id = int(boxes.id[i].item())
                            cid = int(boxes.cls[i].item())
                            conf = float(boxes.conf[i].item())
                            
                            if box_id not in self.tracked_ids:
                                self.tracked_ids.add(box_id)
                                names = self.cfg["class_names"]
                                cname = names[cid] if cid < len(names) else f"Class {cid}"
                                
                                # Gửi lệnh xuống hàng đợi thay vì gọi blocking requests
                                self._http_queue.put((cid, cname, conf))
                                
                                # Update UI
                                self.after(0, lambda c=cid, n=cname, v=conf: self._show_detection(c, n, v))
                                self._log(f"Phát hiện vật thể mới [ID:{box_id}] - {cname} ({conf:.1%})", Theme.INFO)
                                
                except Exception as e:
                    self._log("", f"Lỗi Tracking: {e}", Theme.DANGER)

            with self._det_frame_lock:
                self._det_frame = annotated

            time.sleep(0.03)

    def _http_worker(self):
        """Worker Thread xử lý giao tiếp ESP32, không làm treo luồng YOLO"""
        while self.is_running:
            try:
                cid, cname, conf = self._http_queue.get(timeout=1.0)
                self.after(0, lambda: self.lbl_det_status.configure(text=" Đang gửi lệnh qua HTTP...", text_color=Theme.WARNING))
                
                self._log(f"Gửi tín hiệu Class {cid} ({cname}) xuống ESP32...", Theme.INFO)
                result = self.esp32.send_sort(cid)

                if result.get("status") == "error":
                    self._log(f"ESP32 lỗi: {result.get('message')}", Theme.DANGER)
                    self.after(0, lambda: self.lbl_det_status.configure(text=" Lỗi kết nối ESP32!", text_color=Theme.DANGER))
                else:
                    rt = self.esp32.last_response_time
                    self._log(f"ESP32 đã tiếp nhận lệnh phân loại ({rt:.3f}s)", Theme.SUCCESS)
                    
                    # Lưu vào SQLite Database
                    try:
                        self.cursor.execute("INSERT INTO sort_log (class_id, class_name, conf) VALUES (?, ?, ?)", (cid, cname, conf))
                        self.conn.commit()
                    except Exception as db_e:
                        self._log(f"Lỗi lưu Database: {db_e}", Theme.DANGER)

                    self.stats[cid] += 1
                    self.total += 1
                    self.after(0, lambda: self.lbl_det_status.configure(
                        text=f" ESP32 đã tiếp nhận lệnh phân loại", 
                        text_color=Theme.SUCCESS))                    
                    self.after(0, self._refresh_stats)
                    self._push_firebase()
                
            except Empty:
                pass
            except Exception as e:
                self._log( f"HTTP Worker error: {e}", Theme.DANGER)

    def _push_firebase(self):
        fb_url = self.cfg["firebase_url"]
        if not fb_url: return
        
        url = f"{fb_url.rstrip('/')}/smarttrash/live_stats.json"
        
        names = self.cfg["class_names"]
        stat_dict = {}
        for i, name in enumerate(names):
            stat_dict[name] = self.stats.get(i, 0)
            
        data = {
            "total": self.total,
            "stats": stat_dict,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        def _do_push():
            try:
                requests.put(url, json=data, timeout=3)
                self._log("Đã đồng bộ lên Firebase Cloud!", Theme.INFO)
            except Exception as e:
                self._log(f"Lỗi đồng bộ Firebase: {e}", Theme.WARNING)
                
        threading.Thread(target=_do_push, daemon=True).start()

    def _show_detection(self, cid, cname, conf):
        color = Theme.CLASS_COLORS[cid] if cid < len(Theme.CLASS_COLORS) else Theme.INFO
        icon  = Theme.CLASS_ICONS[cid]  if cid < len(Theme.CLASS_ICONS) else "?"
        self.lbl_det_name.configure(text=f"{icon}  {cname}", text_color=color)
        self.lbl_conf.configure(text=f"{conf:.1%}", text_color=color)
        self.bar_conf.configure(progress_color=color); self.bar_conf.set(conf)

    def _tick_frame(self):
        if self.is_running:
            if self.video.connected and not self._cam_was_connected:
                self._cam_was_connected = True
                self.dot_cam.configure(text_color=Theme.SUCCESS)
                self.lbl_cam.configure(text="Đã kết nối", text_color=Theme.SUCCESS)
            elif not self.video.connected and self._cam_was_connected:
                self._cam_was_connected = False
                self.dot_cam.configure(text_color=Theme.DANGER)
                self.lbl_cam.configure(text="Đang kết nối lại...", text_color=Theme.WARNING)

            frame = None
            if hasattr(self, '_det_frame_lock'):
                with self._det_frame_lock:
                    if hasattr(self, '_det_frame') and self._det_frame is not None:
                        frame = self._det_frame.copy()

            if frame is not None:
                self._render_frame(frame)
                self.lbl_fps.configure(text=f"FPS: {self.video.fps:.1f}")
                self.sb_fps.configure(text=f"FPS: {self.video.fps:.1f}")

            if self.start_time:
                d = datetime.now() - self.start_time
                h, rem = divmod(int(d.total_seconds()), 3600)
                m, s = divmod(rem, 60)
                self.sb_up.configure(text=f"Uptime: {h:02d}:{m:02d}:{s:02d}")

        self.after(33, self._tick_frame)

    def _render_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            lw = self.lbl_video.winfo_width(); lh = self.lbl_video.winfo_height()
            if lw < 2 or lh < 2: return
            h, w = rgb.shape[:2]
            sc = min(lw / w, lh / h)
            nw, nh = int(w * sc), int(h * sc)
            rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
            img = Image.fromarray(rgb)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(nw, nh))
            self.lbl_video.configure(image=ctk_img, text="")
            self.lbl_video._img_ref = ctk_img
        except Exception:
            pass

    def _tick_health(self):
        if self.is_running:
            threading.Thread(target=self._do_health_check, daemon=True).start()
        self.after(10000, self._tick_health)

    def _do_health_check(self):
        ok = self.esp32.check_health()
        self.after(0, lambda: self._update_esp_ui(ok))

    def _update_esp_ui(self, connected):
        if connected:
            self.dot_esp.configure(text_color=Theme.SUCCESS)
            self.lbl_esp.configure(text="Đã kết nối", text_color=Theme.SUCCESS)
        else:
            self.dot_esp.configure(text_color=Theme.DANGER)
            self.lbl_esp.configure(text="Ngắt kết nối", text_color=Theme.DANGER)

    def _refresh_stats(self):
        mx = max(self.stats.values()) if self.stats else 1
        for i, lbl in enumerate(self._stat_lbls):
            cnt = self.stats.get(i, 0)
            lbl.configure(text=str(cnt))
            if i < len(self._stat_bars):
                self._stat_bars[i].set(cnt / max(mx, 1))
        self.lbl_total.configure(text=str(self.total))

    def _reset_stats(self):
        self.stats.clear()
        self.total = 0
        if hasattr(self, 'tracked_ids'):
            self.tracked_ids.clear()
            
        try:
            self.cursor.execute("DELETE FROM sort_log")
            self.conn.commit()
            self._log( "Đã xóa lịch sử trong Database.", Theme.INFO)
        except Exception as db_e:
            self._log(f"Lỗi xóa Database: {db_e}", Theme.DANGER)

        self._refresh_stats()
        self._push_firebase()
        self._log("Đã đặt lại bộ đếm số lượng về 0.", Theme.WARNING)

    def _on_slider(self, v):
        self.lbl_thr.configure(text=f"{v:.0%}")

    def _on_close(self):
        self._log("Đang tắt hệ thống...", Theme.INFO)
        self.is_running = False
        if hasattr(self, 'video') and self.video: self.video.stop()
        self.cfg["confidence_threshold"] = self.slider.get()
        self.cfg["auto_detect"] = self.var_auto.get()
        self.cfg.save()
        if hasattr(self, 'conn'): self.conn.close()
        self.destroy()

if __name__ == "__main__":
    app = TrashClassifierApp()
    app.mainloop()
