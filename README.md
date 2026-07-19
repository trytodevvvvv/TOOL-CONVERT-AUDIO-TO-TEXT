# CapCut Audio to Text Tool

Ứng dụng Desktop viết bằng Python (sử dụng Tkinter cho giao diện) giúp bạn tự động chuyển đổi file Audio/Voice sang văn bản phụ đề bằng thư viện Whisper (chạy local độc lập bên ngoài CapCut) và tự động chèn kết quả trực tiếp vào file cấu trúc dự án `draft_content.json` của CapCut.

---

## 1. Yêu cầu hệ thống và cài đặt

Để chạy được công cụ này, bạn cần cài đặt **Python 3.8+** cùng các thư viện và công cụ bổ trợ sau:

### Bước 1: Cài đặt thư viện Python
Mở Command Prompt (cmd) hoặc terminal và cài đặt thư viện `openai-whisper` cùng các thư viện hỗ trợ:
```bash
pip install openai-whisper
```
*(Hoặc nếu bạn muốn dùng `faster-whisper` cho tốc độ xử lý nhanh hơn trên phần cứng tương thích, bạn có thể tự cài đặt và tích hợp)*

### Bước 2: Cài đặt FFmpeg (Bắt buộc đối với Whisper)
Whisper cần công cụ `ffmpeg` để xử lý âm thanh:
1. Tải **FFmpeg** cho Windows (bản build rút gọn hoặc đầy đủ).
2. Giải nén thư mục FFmpeg.
3. Thêm đường dẫn thư mục `bin` chứa file `ffmpeg.exe` vào biến môi trường **PATH** của hệ thống.
4. Kiểm tra xem đã nhận diện chưa bằng cách mở cmd mới và gõ lệnh: `ffmpeg -version`.

---

## 2. Cách chạy ứng dụng

Chạy file giao diện bằng lệnh sau:
```bash
python capcut_audio_to_text.py
```

---

## 3. Lựa chọn Model Whisper phù hợp cấu hình máy

Trong mục **Tùy chọn chuyển đổi**, bạn có thể chọn kích thước Model Whisper. Dung lượng model lớn sẽ cho độ chính xác cao hơn nhưng yêu cầu phần cứng mạnh mẽ hơn:

| Model | Dung lượng tải về | Tốc độ xử lý | Khuyến nghị cấu hình |
| :--- | :--- | :--- | :--- |
| **tiny** | ~75 MB | Rất nhanh | Máy cấu hình rất yếu, văn bản ngắn |
| **base** | ~140 MB | Nhanh | **Mặc định**, máy văn phòng trung bình, cân bằng tốt |
| **small** | ~460 MB | Trung bình | Máy có card đồ họa rời (NVIDIA GPU), cần độ chính xác cao |
| **medium** | ~1.5 GB | Chậm | Máy cấu hình mạnh, card đồ họa nhiều VRAM |
| **large** | ~3.0 GB | Rất chậm | Máy workstation, máy chủ GPU chuyên dụng |

---

## 4. Hướng dẫn sử dụng chi tiết

1. **Thư mục Drafts CapCut**: Chọn thư mục gốc lưu trữ các project nháp của CapCut. 
   - Trên Windows, đường dẫn mặc định thường là: `C:\Users\<Tên_User>\AppData\Local\CapCut\User Data\Projects\com.lved.pc`
2. **Đường dẫn Draft cụ thể**: Nếu bạn muốn xử lý 1 project cố định nằm ngoài thư mục trên, hãy chọn trực tiếp thư mục của dự án đó (chứa file `draft_content.json`).
3. **File Audio đầu vào**: Chọn file âm thanh của bạn (`.mp3`, `.wav`, `.m4a`, `.mp4`).
4. **Cấu hình thông số**: Chọn ngôn ngữ voice, model Whisper và tích chọn **Chạy thử nghiệm (Dry-Run)** để xem trước kết quả trong Log mà không ghi đè vào file.
5. **Thực hiện**: Bấm nút **CHUYỂN ĐỔI VOICE → TEXT**. Log sẽ chạy và hiển thị tiến trình theo thời gian thực.
6. **Sau khi chạy thử thành công**: Bỏ chọn *Dry-Run* và bấm lại nút để áp dụng trực tiếp. Công cụ sẽ tự động sao lưu file `draft_content.json` thành `.bak` trước khi lưu file mới.
