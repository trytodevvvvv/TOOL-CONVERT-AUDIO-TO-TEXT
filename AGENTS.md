# AGENTS GUIDELINES & WORKFLOW RULES

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
- **CHỈ ĐÓNG GÓI KHI CÓ CHỈ THỊ RÕ RÀNG TỪ NGƯỜI DÙNG (MANDATORY)**:
  + **TUYỆT ĐỐI KHÔNG** tự ý chạy script đóng gói (`python build_package.py`) hay tự tạo file nén ZIP phân phối sau khi hoàn thành code/sửa lỗi.
  + **CHỈ ĐƯỢC PHÉP ĐÓNG GÓI** khi người dùng đưa ra chỉ thị hoặc mệnh lệnh rõ ràng: **"đóng gói ứng dụng cho tôi"** (hoặc tương đương bằng văn bản rõ ràng).
  + Giữ cho kho mã nguồn và thư mục làm việc luôn gọn gàng, tránh tốn tài nguyên và thời gian nén lặp lại không cần thiết khi người dùng đang trong quá trình thử nghiệm.
- **Cách ly hoàn toàn qua thư mục tạm (%TEMP%)**:
  + Tuyệt đối **KHÔNG** sinh ra các thư mục build/staging trung gian trong cây thư mục source code (không tạo `build/`, `dist/`, `package/` làm bẩn kho mã nguồn).
  + Toàn bộ quá trình gom file, lọc rác và đóng gói bắt buộc phải thực hiện trong thư mục tạm của hệ điều hành (`tempfile.mkdtemp()`).
  + Bắt buộc tự động xóa sạch hoàn toàn (`shutil.rmtree`) thư mục tạm ngay sau khi tạo xong file nén ZIP, đảm bảo source code luôn nguyên bản 100%.
- **Factory Reset 100% (Xóa sạch dấu vết cá nhân)**:
  + File `config.json` khi đóng gói cho người khác dùng bắt buộc phải là bản mới tinh (Factory Reset):
    `"drafts_dir": ""`, `"output_dir": ""`, `"colab_url": ""`.
  + Tuyệt đối không để sót đường dẫn máy cá nhân (như `D:/CAIDAT/...`, `C:/Users/...`) để khi sang máy người khác, Tool sẽ tự động kích hoạt tính năng dò tìm thư mục CapCut mặc định của chính máy họ (`get_default_drafts_dir()`).
- **Tối ưu tốc độ cài đặt tối đa (Turbo & Offline-First Installation)**:
  + File `install.bat` phải có cơ chế kiểm tra 3 cấp độ (Smart 3-Tier Check):
    1. Ưu tiên kiểm tra `ffmpeg.exe` có sẵn trong thư mục để người dùng chạy ngay lập tức (0.1 giây offline 100%, không cần kết nối mạng).
    2. Kiểm tra `python -c "import imageio_ffmpeg"` trước: nếu thư viện đã tồn tại thì bỏ qua ngay trong 0.05s.
    3. Tuyệt đối **KHÔNG** chạy lệnh `pip install --upgrade pip` gây nghẽn mạng và tốn thời gian vô ích.
    4. Nếu phải cài đặt bổ trợ qua pip, sử dụng các cờ tăng tốc: `--prefer-binary --no-warn-script-location` và hiển thị trực quan tiến trình.
  + File `run.bat` hỗ trợ khởi chạy 1-Click trực tiếp nếu đã có sẵn `ffmpeg.exe`.
- **Loại bỏ 100% tệp rác**:
  + Không bao giờ nén `__pycache__`, `*.pyc`, `*.bak`, `*.log`, hay các file âm thanh/video tạm thử nghiệm vào bản phân phối.
- **Vị trí file phân phối**:
  + File ZIP sau khi đóng gói được xuất ra thư mục cha bên ngoài kho mã nguồn (ví dụ: `..\CapCut_STT_Tool_v2.0.zip`), không làm rác kho Git.

---

## 2. QUY ƯỚC DỰ ÁN CAPCUT AUDIO TO TEXT TOOL
- Giữ an toàn cấu trúc `draft_content.json`, luôn giữ cơ chế sao lưu `.bak`.
- Đảm bảo hiệu năng bộ nhớ RAM/VRAM khi nạp Whisper (`gc.collect()`, `torch.cuda.empty_cache()`).
- Giữ gìn đồng bộ giữa mã nguồn phát triển và thư mục đóng gói `CapCut_STT_Tool/`.
- Không theo dõi file nhị phân lớn (`ffmpeg.exe`, model `*.pt`, rar).
- Khi đóng gói phát hành, bắt buộc tuân thủ quy trình cách ly tuyệt đối trong thư mục tạm theo RULE 3 (bao gồm `vietnamese_compounds.gz` và `budoux_models.gz`).
- Đảm bảo chất lượng phụ đề đa ngôn ngữ (Zero-Gap Pipeline, Siêu từ điển >68k từ ghép tiếng Việt, Google BudouX cho Nhật/Trung, Eojeol cho Hàn). Tối đa 2 dòng / khối, cân đối 45% - 55%.
