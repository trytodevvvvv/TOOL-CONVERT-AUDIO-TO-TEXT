# HARNESS & DEVELOPMENT RULES (QUY TẮC LÀM VIỆC VỚI CODEBASE)

## 1. CÁC NGUYÊN TẮC BẮT BUỘC (MANDATORY RULES)

### 🚨 RULE 1: QUY TẮC ĐẨY CODE LÊN GITHUB
- **TUYỆT ĐỐI KHÔNG** tự ý chạy `git push` lên GitHub sau khi chỉnh sửa code xong.
- **CHỈ ĐƯỢC PHÉP ĐẨY CODE** khi người dùng đưa ra chỉ thị hoặc mệnh lệnh rõ ràng: **"đẩy code lên github"** (hoặc tương đương bằng văn bản rõ ràng).
- Được phép thực hiện commit local nếu cần lưu trữ checkpoint, nhưng push lên remote thì bắt buộc phải có sự cho phép từ người dùng.

### 🚨 RULE 2: LUÔN XÁC NHẬN PHƯƠNG ÁN TỐI ƯU TRƯỚC KHI CODE
- **"luôn xác nhận phương án tối ưu với người dùng , chưa cần code luôn."**
- Khi nhận bất kỳ yêu cầu mới, tính năng mới hoặc yêu cầu sửa lỗi/refactor nào:
  1. Phân tích chi tiết yêu cầu, rà soát tác động đến toàn bộ hệ thống.
  2. Đề xuất phương án thực hiện tối ưu nhất (nêu rõ ưu điểm, hạn chế, các file bị ảnh hưởng).
  3. Dừng lại và xin ý kiến xác nhận của người dùng.
  4. CHỈ bắt đầu chỉnh sửa mã nguồn sau khi người dùng đã phê duyệt phương án.

### 🚨 RULE 3: QUY TẮC ĐÓNG GÓI PHÂN PHỐI SẠCH & CÁCH LY TUYỆT ĐỐI (ZERO-DATA LEAK & ISOLATED PACKAGING)
- **Cách ly hoàn toàn qua thư mục tạm (%TEMP%)**:
  + Tuyệt đối **KHÔNG** sinh ra các thư mục build/staging trung gian trong cây thư mục source code (không tạo `build/`, `dist/`, `package/` làm bẩn kho mã nguồn).
  + Toàn bộ quá trình gom file, lọc rác và đóng gói bắt buộc phải thực hiện trong thư mục tạm của hệ điều hành (`tempfile.mkdtemp()`).
  + Bắt buộc tự động xóa sạch hoàn toàn (`shutil.rmtree`) thư mục tạm ngay sau khi tạo xong file nén ZIP, đảm bảo source code luôn nguyên bản 100%.
- **Factory Reset 100% (Xóa sạch dấu vết cá nhân)**:
  + File `config.json` khi đóng gói cho người khác dùng bắt buộc phải là bản mới tinh (Factory Reset):
    `"drafts_dir": ""`, `"output_dir": ""`, `"colab_url": ""`.
  + Tuyệt đối không để sót đường dẫn máy cá nhân (như `D:/CAIDAT/...`, `C:/Users/...`) để khi sang máy người khác, Tool sẽ tự động kích hoạt tính năng dò tìm thư mục CapCut mặc định của chính máy họ (`get_default_drafts_dir()`).
- **Loại bỏ 100% tệp rác**:
  + Không bao giờ nén `__pycache__`, `*.pyc`, `*.bak`, `*.log`, hay các file âm thanh/video tạm thử nghiệm vào bản phân phối.
- **Vị trí file phân phối**:
  + File ZIP sau khi đóng gói được xuất ra thư mục cha bên ngoài kho mã nguồn (ví dụ: `..\CapCut_STT_Tool_v2.0.zip`), không làm rác kho Git.

---

## 2. KIẾN TRÚC & QUY ƯỚC DỰ ÁN (PROJECT ARCHITECTURE)

### Cấu trúc mã nguồn:
- **`capcut_audio_to_text.py`**: Mã nguồn chính của ứng dụng Desktop (Python + Tkinter + Whisper).
- **`CapCut_STT_Tool/`**: Thư mục đóng gói phân phối cho người dùng cuối (chứa bản chạy độc lập, file `run.bat`, `install.bat`, hướng dẫn sử dụng).
- Khi cập nhật mã nguồn xử lý logic hoặc giao diện ở thư mục gốc hoặc thư mục phân phối, cần đảm bảo tính đồng bộ giữa hai nơi.

### Các nguyên tắc kỹ thuật cốt lõi:
1. **An toàn dữ liệu dự án CapCut**:
   - Trước khi ghi đè file `draft_content.json`, luôn thực hiện sao lưu ra file `.bak` (`draft_content.json.bak`).
   - Kiểm tra cảnh báo nếu tiến trình CapCut đang chạy để tránh việc CapCut ghi đè làm mất phụ đề.
2. **Tối ưu phần cứng & STT**:
   - Tự động nhận diện GPU (CUDA) vs CPU.
   - Khi chạy STT trên GPU/CPU, giải phóng bộ nhớ RAM/VRAM (`gc.collect()`, `torch.cuda.empty_cache()`).
   - Giới hạn số luồng CPU của PyTorch (`torch.set_num_threads(4)`) để tránh đẩy CPU lên 100% gây đơ máy người dùng.
   - Áp dụng Greedy Decoding (`beam_size=1`, `best_of=1`) để tối ưu tốc độ xử lý.
3. **Phân đoạn phụ đề & Ngôn ngữ tiếng Việt**:
   - Bảo toàn ranh giới ngắt câu theo dấu câu (., ?, !, v.v.).
   - Bảo vệ không cắt đôi các từ ghép tiếng Việt có nghĩa (`COMMON_COMPOUND_WORDS`).
   - Giữ độ dài phụ đề hợp lý cho khung hình video (mặc định tối đa 13 từ/đoạn, wrap dòng ở 40 ký tự).
4. **Quản lý Git & Binary**:
   - Tuyệt đối không commit các file nhị phân lớn như `ffmpeg.exe` (100MB) hay checkpoint model `*.pt` vào Git repository. Các file này phải luôn được đưa vào `.gitignore`.

---

## 3. CHECKLIST KIỂM THỬ TRƯỚC KHI BÀN GIAO
- [ ] Cú pháp Python hợp lệ (chạy thử import, parse AST hoặc test script).
- [ ] Không làm phá vỡ cấu trúc JSON của CapCut (`materials`, `tracks`, `segments`).
- [ ] Giao diện Tkinter chạy mượt mà, không bị freeze (các tác vụ nặng phải nằm trong thread riêng).
- [ ] Khi đóng gói phân phối, đảm bảo quy trình cách ly tuyệt đối trong `%TEMP%` và tự hủy thư mục tạm theo RULE 3.
- [ ] Báo cáo lại cho người dùng và chờ lệnh: nếu người dùng nói "đẩy code lên github" thì mới push.
