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

---

## 2. QUY ƯỚC DỰ ÁN CAPCUT AUDIO TO TEXT TOOL
- Giữ an toàn cấu trúc `draft_content.json`, luôn giữ cơ chế sao lưu `.bak`.
- Đảm bảo hiệu năng bộ nhớ RAM/VRAM khi nạp Whisper (`gc.collect()`, `torch.cuda.empty_cache()`).
- Giữ gìn đồng bộ giữa mã nguồn phát triển và thư mục đóng gói `CapCut_STT_Tool/`.
- Không theo dõi file nhị phân lớn (`ffmpeg.exe`, model `*.pt`, rar).
