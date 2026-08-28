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

## 🎙️ BẢNG TỔNG HỢP CÁC CÂU LỆNH ĐIỀU KHIỂN (VOICE COMMAND REFERENCE)

Hệ thống hỗ trợ cả tiếng Việt (có dấu & không dấu), tiếng Anh và tự động đoán nhận dạng qua bộ từ điển âm vị tự học **VoiceMemory**.

### 1. Đánh thức & Kết thúc phiên (Wake & Sleep)

| Câu lệnh tiếng Việt | Câu lệnh tiếng Anh | Tác vụ thực hiện |
| :--- | :--- | :--- |
| *"Jarvis ơi"* / *"Gọi Jarvis"* | *"Hey Jarvis, I need your help"* | Hiện 3D Orb và bắt đầu phiên đàm thoại liên tục (*Chat Mode*) |
| *"Nghỉ ngơi đi"* / *"Đi ngủ đi"* / *"Tắt đi"* | *"Jarvis, go to sleep"* / *"Goodbye"* | Cho Jarvis đi ngủ, ẩn 3D Orb về chế độ nền |
| *(Vỗ tay đôi - Double Clap)* | *(Double Clap)* | Kích hoạt kịch bản mở ứng dụng/nhạc nhanh theo cấu hình |

---

### 2. Điều khiển Vị trí & Kích thước Cửa sổ (Window Management & Snapping)

Sử dụng Windows API (`SetWindowPos` & `ShowWindow`) để di chuyển, chia màn hình và thay đổi kích thước cửa sổ ngay lập tức:

| Câu lệnh tiếng Việt | Câu lệnh tiếng Anh | Tác vụ |
| :--- | :--- | :--- |
| *"Mở lớn cửa sổ"* / *"Phóng to"* | *"Maximize window"* / *"Fullscreen"* | Phóng to toàn màn hình (`SW_MAXIMIZE`) |
| *"Thu nhỏ cửa sổ"* / *"Ẩn cửa sổ"* | *"Minimize window"* | Thu nhỏ cửa sổ xuống Taskbar (`SW_MINIMIZE`) |
| *"Kéo lên góc trên bên phải"* | *"Snap top right"* / *"Top right"* | Căn cửa sổ vào góc trên bên phải màn hình |
| *"Kéo lên góc trên bên trái"* | *"Snap top left"* / *"Top left"* | Căn cửa sổ vào góc trên bên trái màn hình |
| *"Kéo xuống góc dưới bên phải"* | *"Snap bottom right"* / *"Bottom right"* | Căn cửa sổ vào góc dưới bên phải màn hình |
| *"Kéo xuống góc dưới bên trái"* | *"Snap bottom left"* / *"Bottom left"* | Căn cửa sổ vào góc dưới bên trái màn hình |
| *"Kéo sang trái"* / *"Nửa trái"* / *"Chia đôi sang trái"* | *"Snap left"* / *"Half left"* | Căn cửa sổ chiếm 1/2 màn hình bên trái |
| *"Kéo sang phải"* / *"Nửa phải"* / *"Chia đôi sang phải"* | *"Snap right"* / *"Half right"* | Căn cửa sổ chiếm 1/2 màn hình bên phải |
| *"Đưa vào giữa"* / *"Giữa màn hình"* | *"Center window"* | Đưa cửa sổ về chính giữa màn hình |
| *"Khôi phục kích thước"* | *"Restore window"* | Khôi phục kích thước bình thường |
| *"Đổi cửa sổ"* / *"Chuyển cửa sổ"* | *"Switch window"* / *"Next window"* | Chuyển qua lại giữa các ứng dụng (`Alt + Tab`) |
| *"Chuyển sang Chrome / VS Code / Spotify"* | *"Switch to Chrome / VS Code"* | Kích hoạt thẳng ứng dụng mong muốn |
| *"Đóng cửa sổ"* / *"Tắt cửa sổ"* | *"Close window"* / *"Close Chrome"* | Đóng cửa sổ ứng dụng đang mở (`Alt + F4`) |

---

### 3. Nhận diện & Điều hướng Tab Trình duyệt (Tab Management)

Điều khiển trực tiếp các thẻ Tab trong Chrome, Edge, Firefox, VS Code:

| Câu lệnh tiếng Việt | Phím tắt thực thi | Tác vụ |
| :--- | :--- | :--- |
| *"Tab tiếp theo"* / *"Chuyển tab"* / *"Next tab"* | `Ctrl + Tab` | Chuyển sang thẻ tab bên phải liền kề |
| *"Tab trước"* / *"Quay lại tab"* / *"Previous tab"* | `Ctrl + Shift + Tab` | Chuyển về thẻ tab bên trái |
| *"Chọn tab 1"* / *"Tab 1"* / *"Tab đầu tiên"* | `Ctrl + 1` | Nhảy thẳng đến Tab số 1 |
| *"Chọn tab 2"* / *"Tab 2"* / *"Tab thứ 2"* | `Ctrl + 2` | Nhảy thẳng đến Tab số 2 |
| *"Chọn tab 3"* / *"Tab 3"* / *"Tab thứ 3"* | `Ctrl + 3` | Nhảy thẳng đến Tab số 3 |
| *"Chọn tab 4"* / *"Tab 4"* | `Ctrl + 4` | Nhảy thẳng đến Tab số 4 |
| *"Chọn tab cuối cùng"* / *"Last tab"* | `Ctrl + 9` | Nhảy thẳng đến Tab cuối cùng |
| *"Mở tab mới"* / *"Tạo tab mới"* / *"New tab"* | `Ctrl + T` | Mở một tab trống mới |
| *"Đóng tab"* / *"Tắt tab"* / *"Close tab"* | `Ctrl + W` | Đóng tab đang xem hiện tại |
| *"Mở lại tab vừa đóng"* / *"Khôi phục tab"* | `Ctrl + Shift + T` | Mở lại tab vừa vô tình đóng |

---

### 4. Tìm kiếm Thông minh theo Ngữ cảnh (Context-Aware Search)

Hệ thống tự động phát hiện cửa sổ đang hoạt động để tìm kiếm tại chỗ mà **không mở thêm cửa sổ/tab trùng lặp**:

| Ngữ cảnh hiện tại | Câu lệnh giọng nói | Hành vi của Jarvis |
| :--- | :--- | :--- |
| **Đang ở YouTube** | *"Tìm cho tôi nhạc chill"* / *"Search Lady Gaga"* | Tự động click vào thanh tìm kiếm YouTube hiện tại, gõ từ khóa tiếng Việt và ấn `Enter`. |
| **Đang ở Trình duyệt** | *"Tìm kiếm tài liệu Python"* / *"Search ChatGPT"* | Tự động focus thanh địa chỉ (`Ctrl + L`), dán từ khóa và tìm kiếm trực tiếp trên tab hiện tại. |
| **Đang ở VS Code** | *"Tìm hàm get_active_window"* | Kích hoạt tìm kiếm toàn cục trong project (`Ctrl + Shift + F`). |
| **Bất kỳ đâu** | *"Mở browser và tìm cho tôi ChatGPT"* | Mở trình duyệt Chrome mới và điều hướng đến kết quả Google Search. |

---

### 5. Tương tác Thực thể YouTube & Chuỗi lệnh (YouTube UI Interaction)

| Câu lệnh giọng nói | Tác vụ thực hiện |
| :--- | :--- |
| *"Play video 1"* / *"Bật video 1"* / *"Chọn video đầu tiên"* | Nhận diện tọa độ thẻ Video 1 ($X:35\%, Y:45\%$) và click phát ngay lập tức. |
| *"Play video 2"* / *"Bật video 2"* / *"Chọn video thứ 2"* | Nhận diện tọa độ thẻ Video 2 ($X:72\%, Y:45\%$) và click phát ngay. |
| *"Play video 3"* / *"Bật video 3"* / *"Chọn video thứ 3"* | Click phát thẻ Video 3 ($X:35\%, Y:80\%$). |
| *"Play video 4"* / *"Chọn video thứ 4"* | Click phát thẻ Video 4 ($X:72\%, Y:80\%$). |
| *"Tạm dừng"* / *"Tiếp tục"* / *"Play"* / *"Pause"* | Gửi phím `k` để Play / Pause video YouTube. |
| *"Toàn màn hình"* / *"Fullscreen"* | Gửi phím `f` để phóng to trình phát YouTube. |
| *"Tắt tiếng"* / *"Bật tiếng"* / *"Mute"* / *"Unmute"* | Gửi phím `m` để bật/tắt tiếng YouTube. |
| **Chuỗi lệnh:** *"Mở YouTube tìm nhạc lofi và chọn video đầu tiên"* | Jarvis tự động: Mở YouTube $\rightarrow$ Chờ trang tải $\rightarrow$ Tắt popup dịch $\rightarrow$ Gõ từ khóa $\rightarrow$ Click phát video 1! |

---

### 6. Mở Ứng dụng & Tiện ích Hệ thống (Apps & System Tools)

| Câu lệnh giọng nói | Tác vụ thực hiện |
| :--- | :--- |
| *"Mở Chrome"* / *"Mở browser"* / *"Open Chrome"* | Khởi chạy trình duyệt Google Chrome |
| *"Mở VS Code"* / *"Open VS Code"* / *"Mở code"* | Khởi chạy Visual Studio Code |
| *"Mở Antigravity"* / *"Open Antigravity"* | Khởi chạy Antigravity IDE |
| *"Mở Spotify"* / *"Open Spotify"* | Khởi chạy Spotify |
| *"Mở Notepad"* / *"Mở Calculator"* / *"Mở Explorer"* | Mở các ứng dụng công cụ Windows |
| *"Kiểm tra hệ thống"* / *"System status"* | Báo cáo chi tiết phần trăm CPU, RAM, Disk qua giọng nói |
| *"Tìm file vừa tải"* / *"Find latest file"* | Tìm đường dẫn file mới nhất trong thư mục Downloads |

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
Phát hiện Wake Phrase -> Cửa sổ 3D Orb xuất hiện
        ↓
Orb thực hiện Wake Animation (Pulse + Ripple + Glow)
        ↓
[ LISTENING ] -> Hạt Orb & Surface Radar phản hồi theo âm lượng giọng nói thật
        ↓
[ PROCESSING ] -> SmartSTT nhận diện câu lệnh -> Hermes Agent lập kế hoạch đa bước
        ↓
[ ACTING ] -> Tự động thao tác chuột, bàn phím, điều hướng cửa sổ và tab
        ↓
[ SPEAKING ] -> Orb phát giọng nói AI phản hồi
        ↓
[ LISTENING ] -> Phiên đàm thoại tiếp tục (UI không tự tắt sau 1 câu)
        ↓
Hết phiên làm việc (hoặc sau 45s im lặng / nói "Go to sleep") -> Orb tự ẩn về chế độ chờ
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
