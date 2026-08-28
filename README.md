# Jarvis Assistant — AI Brain & 3D Reactive Holographic Orb

Hệ thống trợ lý ảo thông minh Jarvis hoạt động ngầm (background daemon) kết hợp giao diện 3D Holographic Earth Orb (Three.js WebGL). Giao diện hoàn toàn ẩn khi ở chế độ chờ và chỉ xuất hiện khi được gọi bằng giọng nói.

---

## ⚡ Kiến trúc hệ thống (Wake-to-UI Architecture)

```text
                  ┌──────────────────────────┐
                  │      JARVIS PYTHON       │
                  │        BACKGROUND        │
                  │                          │
Mic ─────────────►│ Wake / Clap Detection    │
                  │ Speech Recognition       │
                  │ Command Engine           │
                  │ ElevenLabs / System TTS  │
                  └────────────┬─────────────┘
                               │
                       WebSocket (ws://127.0.0.1:8765)
                               │
                               ▼
                  ┌──────────────────────────┐
                  │      JARVIS ORB UI       │
                  │ (Desktop Window/Browser) │
                  │                          │
                  │     🌐 3D EARTH ORB      │
                  │                          │
                  └──────────────────────────┘
                        ↑              ↑
                   show/hide       audio level
```

---

## 🌌 Trải nghiệm người dùng (Core UX Flow)

```text
Khởi động máy tính / Chạy Jarvis ngầm
        ↓
Microphone listener chạy nền liên tục
        ↓
KHÔNG CÓ CỬA SỔ, KHÔNG CÓ OVERLAY, KHÔNG CÓ HUD
        ↓
Người dùng gọi: "Jarvis, I need your help" (hoặc "Hey Jarvis")
        ↓
Phát hiện Wake Phrase -> Cửa sổ Orb xuất hiện
        ↓
Orb thực hiện Wake Animation (Pulse + Ripple + Glow)
        ↓
[ LISTENING ] -> Hạt Orb & Surface Radar phản hồi theo âm lượng giọng nói thật
        ↓
[ PROCESSING ] -> Thực thi lệnh (mở VS Code, Chrome, Antigravity, Spotify...)
        ↓
[ SPEAKING ] -> Orb phản hồi theo âm thanh ElevenLabs / TTS
        ↓
[ LISTENING ] -> Cuộc trò chuyện tiếp tục (UI không tự tắt sau 1 câu)
        ↓
Hết phiên làm việc (hoặc sau thời gian chờ) -> Cửa sổ Orb tự ẩn về chế độ chờ
```

---

## 🚀 Cài đặt & Khởi chạy

1. Cài đặt các thư viện cần thiết:
```bash
python -m pip install -r requirements.txt
```

2. Khởi chạy toàn bộ hệ thống (Backend + Desktop UI Overlay):
```bash
python jarvis.py
```

3. (Tùy chọn) Chạy giao diện Web demo độc lập trên trình duyệt:
```bash
python serve_orb.py
```

---

## ⌨️ Phím tắt Chế độ Phát triển (Dev Mode Controls)

Khi đang mở giao diện Orb, bạn có thể sử dụng các phím tắt sau để kiểm thử nhanh:
- `1` ➔ **Hidden**: Ẩn giao diện về chế độ chờ
- `2` ➔ **Wake**: Kích hoạt chuỗi hiệu ứng thức tỉnh (Wake sequence)
- `3` ➔ **Listening**: Chế độ đang lắng nghe (Mic live amplitude)
- `4` ➔ **Processing**: Chế độ đang xử lý tác vụ
- `5` ➔ **Speaking**: Chế độ đang phát giọng nói
- `6` ➔ **End Session**: Kết thúc phiên làm việc
- `Space` ➔ Kích hoạt sóng xung kích bề mặt (Surface ripple pulse)
- `H` ➔ Bật / tắt thanh trạng thái Dev HUD

---

## ⚙️ Biến môi trường (.env) & Tùy chỉnh

| Biến môi trường | Mặc định | Ý nghĩa |
| --------------- | -------- | ------- |
| `JARVIS_WS_PORT` | `8765` | Cổng WebSocket nội bộ kết nối Backend và UI. |
| `JARVIS_LAUNCH_DESKTOP_UI` | `True` | Tự động mở cửa sổ Desktop Overlay không viền khi khởi động `jarvis.py`. |
| `JARVIS_SESSION_TIMEOUT_S` | `45.0` | Số giây không có tương tác trước khi Orb tự động ẩn về chế độ nền. |
| `REQUIRE_WAKE_WORD` | `True` | Bắt buộc nói "Hey Jarvis" trước khi vỗ tay / ra lệnh. |
| `WAKE_WINDOW_S` | `8.0` | Số giây cửa sổ chờ nhận diện tiếng vỗ tay sau khi nói wake-word. |
| `WAKE_FEEDBACK_ENABLED` | `True` | Phản hồi âm thanh / giọng nói khi nhận diện được từ khóa đánh thức. |
| `WAKE_FEEDBACK_PHRASE` | `Yes sir?` | Câu thoại phản hồi khi được đánh thức. |
| `ELEVENLABS_API_KEY` | *(Tùy chọn)* | API Key từ ElevenLabs cho giọng đọc AI chất lượng cao. |
| `ELEVENLABS_VOICE_ID` | *(Tùy chọn)* | Voice ID giọng Jarvis trên ElevenLabs. |
| `JARVIS_LAYOUT_MODE` | `4_split` | Chế độ chia cửa sổ: `4_split` (lưới 2x2), `2_split`, `3_split`, `none`. |
| `JARVIS_SAMPLE_RATE` | `16000` | Tần số lấy mẫu tối ưu cho AI nhận diện giọng nói. |
