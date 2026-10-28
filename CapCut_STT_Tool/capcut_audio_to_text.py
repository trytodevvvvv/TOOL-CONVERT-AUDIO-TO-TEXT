import os
import sys
import json
import uuid
import shutil
import datetime
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ==========================================
# THIẾT LẬP MÔI TRƯỜNG & ĐƯỜNG DẪN HỆ THỐNG
# ==========================================

def setup_ffmpeg_path():
    """
    Tự động dò tìm và nạp đường dẫn FFmpeg vào PATH để Whisper sử dụng được
    ngay cả khi người dùng chưa cấu hình biến môi trường thủ công.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Kiểm tra trong thư mục hiện tại hoặc thư mục con ffmpeg
    candidates = [
        current_dir,
        os.path.join(current_dir, "ffmpeg"),
        os.path.join(current_dir, "ffmpeg", "bin")
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.exists(os.path.join(c, "ffmpeg.exe")):
            if c not in os.environ.get("PATH", ""):
                os.environ["PATH"] = c + os.pathsep + os.environ.get("PATH", "")
            return
            
    if shutil.which("ffmpeg"):
        return
            
    # 2. Tự động trích xuất binary của imageio_ffmpeg nếu người dùng đã cài qua pip
    try:
        import importlib
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        ffmpeg_exe = getattr(imageio_ffmpeg, "get_ffmpeg_exe", lambda: "")()
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)
            target_ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            if not os.path.exists(target_ffmpeg):
                try:
                    shutil.copyfile(ffmpeg_exe, target_ffmpeg)
                except Exception:
                    pass
            # Sao chép vào thư mục tool để dùng offline sau này
            local_ffmpeg = os.path.join(current_dir, "ffmpeg.exe")
            if not os.path.exists(local_ffmpeg):
                try:
                    shutil.copyfile(ffmpeg_exe, local_ffmpeg)
                except Exception:
                    pass
            os.environ["PATH"] = current_dir + os.pathsep + ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

# Khởi chạy nạp FFmpeg ngay khi import
setup_ffmpeg_path()

def get_default_drafts_dir():
    """
    Tự động dò tìm thư mục lưu trữ dự án mặc định của CapCut PC trên máy người dùng.
    """
    possible_roots = []
    
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        possible_roots.append(os.path.join(local_app_data, "CapCut", "User Data", "Projects", "com.lved.pc"))
        
    user_home = os.path.expanduser("~")
    possible_roots.append(os.path.join(user_home, "AppData", "Local", "CapCut", "User Data", "Projects", "com.lved.pc"))
    
    for r in possible_roots:
        if os.path.exists(r) and os.path.isdir(r):
            return r.replace("\\", "/")
            
    return ""

# ==========================================
# PART 1: PROCESSING LOGIC (Tkinter Independent)
# ==========================================

def find_drafts(drafts_root):
    """
    Quét thư mục gốc chứa các dự án CapCut.
    Trả về danh sách dict: {"name": Tên dự án, "path": Đường dẫn thư mục, "status": Trạng thái}
    """
    drafts = []
    if not drafts_root or not os.path.exists(drafts_root) or not os.path.isdir(drafts_root):
        return drafts
    
    try:
        for item in os.listdir(drafts_root):
            item_path = os.path.join(drafts_root, item)
            if os.path.isdir(item_path):
                draft_content_path = os.path.join(item_path, "draft_content.json")
                meta_path = os.path.join(item_path, "draft_meta_info.json")
                
                # Xác định tên hiển thị của dự án (lấy từ metadata nếu có, nếu không lấy tên thư mục)
                project_name = item
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta_data = json.load(f)
                            project_name = meta_data.get("draft_name", item)
                    except Exception:
                        pass
                
                if os.path.exists(draft_content_path):
                    status = "Sẵn sàng (Ready)"
                    
                    drafts.append({
                        "name": project_name,
                        "path": item_path,
                        "status": status
                    })
    except Exception as e:
        print(f"Lỗi khi quét thư mục drafts: {e}")
        
    return drafts

def find_audio_candidates(project_path):
    """
    Tìm kiếm danh sách các file audio/video thực sự được kéo vào timeline (tracks)
    trong file cấu trúc draft_content.json.
    """
    supported_exts = ('.mp3', '.wav', '.m4a', '.mp4', '.aac')
    candidates = []
    
    draft_content_path = os.path.join(project_path, "draft_content.json")
    if not os.path.exists(draft_content_path):
        return candidates
        
    try:
        with open(draft_content_path, "r", encoding="utf-8") as f:
            draft_data = json.load(f)
            
        materials = draft_data.get("materials", {})
        
        # Tạo bản đồ từ material_id sang đường dẫn file để tra cứu nhanh
        material_path_map = {}
        for category in ["audios", "videos"]:
            for item in materials.get(category, []):
                mat_id = item.get("id")
                path = item.get("local_material_path") or item.get("path")
                if mat_id and path:
                    material_path_map[mat_id] = os.path.normpath(path)
                    
        # Duyệt qua các track trên timeline để tìm các segment đang hoạt động
        audio_candidates = []
        video_candidates = []
        for track in draft_data.get("tracks", []):
            t_type = track.get("type")
            if t_type == "audio":
                for segment in track.get("segments", []):
                    mat_id = segment.get("material_id")
                    if mat_id and mat_id in material_path_map:
                        file_path = material_path_map[mat_id]
                        if os.path.exists(file_path) and file_path.lower().endswith(supported_exts):
                            # Tính toán timeline offset
                            target_range = segment.get("target_timerange", {})
                            source_range = segment.get("source_timerange") or {}
                            target_start = target_range.get("start", 0)
                            source_start = source_range.get("start", 0) if source_range else 0
                            offset_us = target_start - source_start
                            
                            # Tránh trùng lặp đường dẫn
                            if not any(c["path"] == file_path for c in audio_candidates):
                                audio_candidates.append({
                                    "path": file_path,
                                    "offset_us": offset_us
                                })
            elif t_type == "video":
                for segment in track.get("segments", []):
                    mat_id = segment.get("material_id")
                    if mat_id and mat_id in material_path_map:
                        file_path = material_path_map[mat_id]
                        if os.path.exists(file_path) and file_path.lower().endswith(supported_exts):
                            # Tính toán timeline offset
                            target_range = segment.get("target_timerange", {})
                            source_range = segment.get("source_timerange") or {}
                            target_start = target_range.get("start", 0)
                            source_start = source_range.get("start", 0) if source_range else 0
                            offset_us = target_start - source_start
                            
                            if not any(c["path"] == file_path for c in video_candidates):
                                video_candidates.append({
                                    "path": file_path,
                                    "offset_us": offset_us
                                })
                                
        # Ưu tiên các file trên track audio lên hàng đầu
        candidates = audio_candidates + video_candidates
    except Exception as e:
        pass
        
    return candidates

# Bộ nhớ đệm lưu trữ model Whisper đã load nhằm tránh nạp lại nhiều lần
_MODEL_CACHE = {}

def transcribe_audio(audio_path, language, model_size, log_callback):
    """
    Gọi Whisper để chuyển đổi file audio sang văn bản.
    Trả về list segment: [{"start": giây, "end": giây, "text": str}]
    """
    log_callback(f"Bắt đầu quá trình nhận diện giọng nói cho: {os.path.basename(audio_path)}")
    log_callback("Kiểm tra và import thư viện Whisper...")
    
    try:
        import whisper
    except ImportError:
        log_callback("[LỖI THIẾU THƯ VIỆN] Không tìm thấy thư viện 'openai-whisper'.")
        log_callback("Vui lòng cài đặt bằng lệnh: pip install openai-whisper")
        log_callback("Ngoài ra, hãy đảm bảo hệ thống đã cài đặt 'ffmpeg' và thêm vào PATH.")
        raise ImportError("Thư viện 'openai-whisper' chưa được cài đặt.")
        
    global _MODEL_CACHE
    
    # Đảm bảo ffmpeg đã được cấu hình đường dẫn
    setup_ffmpeg_path()
    if not shutil.which("ffmpeg"):
        log_callback("[CẢNH BÁO] Không tìm thấy FFmpeg trong hệ thống!")
        log_callback("Whisper cần FFmpeg để giải mã âm thanh. Hãy chạy file install.bat hoặc đặt ffmpeg.exe vào thư mục tool.")
    
    # Kiểm tra xem GPU CUDA có khả dụng không để tối ưu phần cứng
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log_callback(f"Phát hiện thiết bị xử lý STT: {device.upper()}")
    
    # Kiểm tra xem file model đã được tải về máy chưa
    user_home = os.path.expanduser("~")
    model_file_path = os.path.join(user_home, ".cache", "whisper", f"{model_size}.pt")
    is_downloaded = os.path.exists(model_file_path)
    
    # Giải phóng các model cũ khác ra khỏi cache để dọn sạch RAM/VRAM
    other_models = [m for m in list(_MODEL_CACHE.keys()) if m != model_size]
    for m in other_models:
        del _MODEL_CACHE[m]
        
    if model_size in _MODEL_CACHE:
        log_callback(f"Đã sử dụng model Whisper '{model_size}' sẵn có trong RAM (Không cần load lại).")
        model = _MODEL_CACHE[model_size]
    else:
        if is_downloaded:
            log_callback(f"Đang đọc model Whisper '{model_size}' từ file đã tải trên máy...")
        else:
            log_callback(f"Đang tải model Whisper '{model_size}' (quá trình này có thể mất vài phút ở lần đầu chạy)...")
            
        try:
            model = whisper.load_model(model_size, device=device)
            _MODEL_CACHE[model_size] = model
        except Exception as e:
            log_callback(f"[LỖI TẢI MODEL] Không thể tải model Whisper '{model_size}': {e}")
            raise e
        
    log_callback("Đang xử lý chuyển đổi audio thành văn bản...")
    log_callback("Đã áp dụng chế độ tối ưu hóa phần cứng (Greedy Decoding & FP16 Auto)...")
    
    # Chuẩn bị tham số tối ưu nhiệt độ và tốc độ
    kwargs = {
        "fp16": (device == "cuda"), # Tắt fp16 trên CPU để tránh mô phỏng gây nóng máy và chậm
        "beam_size": 1,             # Sử dụng giải thuật Greedy Decoding (beam_size=1) giúp giảm 80% tải tính toán
        "best_of": 1                # Không chạy thử nhiều luồng giúp tiết kiệm điện năng
    }
    
    if language:
        kwargs["language"] = language
        log_callback(f"Ngôn ngữ được chỉ định: {language}")
    else:
        log_callback("Đang tự động nhận diện ngôn ngữ voice...")
        
    try:
        # Giới hạn số luồng CPU của PyTorch để tránh CPU bị đẩy lên 100% gây nóng máy
        torch.set_num_threads(4)
        
        # Tiến hành transcribe với các tham số tối ưu và tắt tính toán Gradient (no_grad) giúp tiết kiệm điện/VRAM
        with torch.no_grad():
            result = model.transcribe(audio_path, **kwargs)
        segments = result.get("segments", [])
        
        parsed_segments = []
        for seg in segments:
            parsed_segments.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": str(seg["text"]).strip()
            })
            
        log_callback(f"Chuyển đổi hoàn tất! Sinh ra {len(parsed_segments)} đoạn văn bản.")
        
        # Giải phóng VRAM CUDA và dọn dẹp bộ nhớ RAM rác
        if device == "cuda":
            torch.cuda.empty_cache()
        import gc
        gc.collect()
        
        return parsed_segments
        
    except Exception as e:
        log_callback(f"[LỖI XỬ LÝ AUDIO] Gặp lỗi trong quá trình chạy STT: {e}")
        raise e

def wrap_text(text, max_chars=40):
    """
    Tự động xuống dòng khi câu quá dài (gần hết khung hình) mà không cắt đôi từ.
    Độ dài mặc định 40 ký tự là tối ưu cho khung hình video ngang thông dụng.
    """
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        word_len = len(word)
        # +1 cho dấu cách nếu không phải từ đầu tiên của dòng
        added_len = word_len + (1 if current_line else 0)
        if current_length + added_len <= max_chars:
            current_line.append(word)
            current_length += added_len
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = word_len
            
    if current_line:
        lines.append(" ".join(current_line))
        
    return "\n".join(lines)

COMMON_COMPOUND_WORDS = {
    "giông bão", "dông bão", "sóng gió", "đau khổ", "hạnh phúc", "yêu thương",
    "nhân quả", "nghiệp báo", "bình an", "tự tại", "trí tuệ", "giác ngộ",
    "từ bi", "vô thường", "luân hồi", "giải thoát", "buông thư", "hiện tại",
    "quá khứ", "tương lai", "tổn thương", "mệt mỏi", "đau buồn", "thiện lương",
    "phật pháp", "tu hành", "cuộc sống", "tâm hồn", "tinh thần", "gia đình",
    "sự nghiệp", "thành công", "thất bại", "sinh tử", "đất trời", "núi sông",
    "gió sương", "mưa nắng", "ngày đêm", "học tập", "làm việc", "vui vẻ",
    "phút giây", "giây phút", "miệng cười"
}

def clean_word(word):
    import re
    return re.sub(r'[^\w\s]', '', word).lower().strip()

def split_segments_by_words(segments, max_words=13):
    """
    Chia nhỏ các đoạn segment có số lượng từ vượt quá max_words (mặc định 13 từ).
    Phân phối các từ đều nhau giữa các đoạn để tránh việc đoạn cuối cùng chỉ có 1-2 từ lẻ loi.
    Đồng thời tự động bảo vệ không cắt đôi các từ ghép tiếng Việt có nghĩa.
    """
    new_segments = []
    for seg in segments:
        words = seg["text"].split()
        if len(words) <= max_words:
            new_segments.append(seg)
            continue
            
        start_time = seg["start"]
        end_time = seg["end"]
        total_duration = end_time - start_time
        total_words = len(words)
        
        import math
        # Tính số lượng đoạn cần chia
        num_chunks = math.ceil(total_words / max_words)
        # Tính kích thước cơ bản của mỗi đoạn
        base_chunk_size = total_words // num_chunks
        # Số lượng đoạn sẽ có kích thước lớn hơn 1 từ (để phân bổ phần dư)
        remainder = total_words % num_chunks
        
        # Xác định kích thước cụ thể cho từng đoạn
        chunk_sizes = []
        for i in range(num_chunks):
            size = base_chunk_size + (1 if i < remainder else 0)
            chunk_sizes.append(size)
            
        # Xác định các chỉ số biên chia tách (split indices) ban đầu
        split_indices = []
        curr_idx = 0
        for size in chunk_sizes[:-1]:
            curr_idx += size
            split_indices.append(curr_idx)
            
        # 1. Điều chỉnh biên chia để ưu tiên ngắt tại dấu câu (dấu phẩy, dấu chấm, dấu hỏi,...) nhằm giữ nguyên cấu trúc vế câu có nghĩa
        for i in range(len(split_indices)):
            split_idx = split_indices[i]
            prev_split = split_indices[i - 1] if i > 0 else 0
            next_split = split_indices[i + 1] if i < len(split_indices) - 1 else total_words
            
            best_adj_idx = None
            min_dist = 999
            
            # Quét tìm dấu câu trong khoảng lân cận từ split_idx - 3 đến split_idx + 2
            start_search = max(prev_split + 1, split_idx - 3)
            end_search = min(next_split - 1, split_idx + 2)
            
            for adj_idx in range(start_search, end_search + 1):
                word = words[adj_idx - 1]
                if word and word[-1] in (',', '.', '?', '!', ';', ':', '—', '…', '，', '。', '？', '！', '、', '；', '：'):
                    dist = abs(adj_idx - split_idx)
                    new_prev_size = adj_idx - prev_split
                    new_next_size = next_split - adj_idx
                    if new_prev_size <= max_words and new_next_size <= max_words:
                        if dist < min_dist:
                            min_dist = dist
                            best_adj_idx = adj_idx
                            
            if best_adj_idx is not None:
                split_indices[i] = best_adj_idx

        # 2. Điều chỉnh biên chia để tránh cắt đôi từ ghép tiếng Việt có nghĩa ở ranh giới các đoạn
        for i in range(len(split_indices)):
            split_idx = split_indices[i]
            if split_idx > 0 and split_idx < total_words:
                w1 = clean_word(words[split_idx - 1])
                w2 = clean_word(words[split_idx])
                compound = f"{w1} {w2}"
                if compound in COMMON_COMPOUND_WORDS:
                    prev_split = split_indices[i - 1] if i > 0 else 0
                    next_split = split_indices[i + 1] if i < len(split_indices) - 1 else total_words
                    
                    right_prev_size = (split_idx + 1) - prev_split
                    left_next_size = next_split - (split_idx - 1)
                    
                    if right_prev_size <= max_words:
                        split_indices[i] = split_idx + 1
                    elif left_next_size <= max_words:
                        split_indices[i] = split_idx - 1
                        
        # Tái tạo lại chunk_sizes từ split_indices đã điều chỉnh
        adjusted_chunk_sizes = []
        prev = 0
        for idx in split_indices:
            adjusted_chunk_sizes.append(idx - prev)
            prev = idx
        adjusted_chunk_sizes.append(total_words - prev)
        chunk_sizes = adjusted_chunk_sizes
            
        # Thực hiện chia tách các đoạn từ theo kích thước đã xác định
        current_word_idx = 0
        time_per_word = total_duration / total_words
        
        for size in chunk_sizes:
            chunk_words = words[current_word_idx : current_word_idx + size]
            chunk_text = " ".join(chunk_words)
            
            # Tính toán start/end dựa trên chỉ số từ
            chunk_start = start_time + current_word_idx * time_per_word
            chunk_end = start_time + (current_word_idx + size) * time_per_word
            
            if chunk_end > end_time or (current_word_idx + size) == total_words:
                chunk_end = end_time
                
            new_segments.append({
                "start": chunk_start,
                "end": chunk_end,
                "text": chunk_text
            })
            
            current_word_idx += size
            
    return new_segments

def get_capcut_font_path():
    """
    Tự động tìm đường dẫn font hệ thống mặc định của ứng dụng CapCut trên máy.
    Hỗ trợ linh hoạt mọi máy người dùng mà không bị hardcode đường dẫn cá nhân.
    """
    possible_app_dirs = []
    
    # 1. Thư mục AppData chuẩn
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        possible_app_dirs.append(os.path.join(local_app_data, "CapCut", "Apps"))
        
    user_home = os.path.expanduser("~")
    possible_app_dirs.append(os.path.join(user_home, "AppData", "Local", "CapCut", "Apps"))
    
    # 2. Tìm kiếm trong các ổ đĩa phổ biến nếu người dùng cài đặt ở ổ khác
    for drive in ["C:", "D:", "E:"]:
        possible_app_dirs.append(os.path.join(drive, "\\", "CapCut", "Apps"))
        possible_app_dirs.append(os.path.join(drive, "\\", "Program Files", "CapCut", "Apps"))
        possible_app_dirs.append(os.path.join(drive, "\\", "Program Files (x86)", "CapCut", "Apps"))
        
    for apps_dir in possible_app_dirs:
        try:
            if os.path.exists(apps_dir):
                versions = [d for d in os.listdir(apps_dir) if os.path.isdir(os.path.join(apps_dir, d))]
                if versions:
                    versions.sort(reverse=True)  # Ưu tiên phiên bản mới nhất
                    for v in versions:
                        for font_candidate in [
                            os.path.join(apps_dir, v, "Resources", "Font", "SystemFont", "en.ttf"),
                            os.path.join(apps_dir, v, "Resources", "Font", "SystemFont", "vi.ttf"),
                            os.path.join(apps_dir, v, "Resources", "Font", "SystemFont", "system.ttf")
                        ]:
                            if os.path.exists(font_candidate):
                                return font_candidate.replace("\\", "/")
        except Exception:
            continue
            
    # 3. Fallback an toàn: Font hệ thống Windows
    windir = os.environ.get("WINDIR", "C:\\Windows")
    windows_font = os.path.join(windir, "Fonts", "arial.ttf")
    if os.path.exists(windows_font):
        return windows_font.replace("\\", "/")
        
    return ""

def insert_text_into_draft(project_path, segments, dry_run, log_callback, timeline_offset_us=0, group_subtitles=True):
    """
    Chèn các đoạn văn bản (subtitles) vào draft_content.json của project.
    """
    draft_content_path = os.path.join(project_path, "draft_content.json")
    if not os.path.exists(draft_content_path):
        raise FileNotFoundError(f"Không tìm thấy file {draft_content_path}")
        
    log_callback(f"Đang đọc file cấu trúc dự án: {draft_content_path}")
    with open(draft_content_path, "r", encoding="utf-8") as f:
        try:
            draft_data = json.load(f)
        except Exception as e:
            log_callback(f"[LỖI] File draft_content.json bị lỗi định dạng: {e}")
            raise e
            
    # Khởi tạo các cấu trúc cơ bản nếu chưa có
    if "materials" not in draft_data:
        draft_data["materials"] = {}
    if "texts" not in draft_data["materials"]:
        draft_data["materials"]["texts"] = []
    if "tracks" not in draft_data:
        draft_data["tracks"] = []
        
    # Luôn tạo một track text mới chuyên biệt cho phụ đề để tránh đè trùng lặp lên các track chữ/tiêu đề có sẵn của bạn
    log_callback("Đang tạo một track text mới chuyên biệt cho phụ đề...")
    text_track = {
        "id": str(uuid.uuid4()).upper(),
        "type": "text",
        "segments": [],
        "flag": 0,
        "attribute": 0,
        "name": "",
        "is_default_name": True
    }
    draft_data["tracks"].append(text_track)
        
    inserted_count = 0
    preview_limit = 5
    
    # Tạo mã nhóm group_id chung cho toàn bộ đợt phụ đề này nếu bật gom nhóm
    import time
    shared_group_id = f"vi-VN_{int(time.time() * 1000)}" if group_subtitles else ""
    font_path = get_capcut_font_path()
    log_callback(f"Nhóm phụ đề ID: {shared_group_id}")
    log_callback(f"Font hệ thống mặc định: {font_path}")
    
    for i, seg in enumerate(segments):
        start_sec = seg["start"]
        end_sec = seg["end"]
        text_content = seg["text"]
        
        # Tự động xuống dòng khi câu quá dài
        text_content_wrapped = wrap_text(text_content, max_chars=40)
        
        # Chuyển đổi giây sang micro giây và cộng thêm độ trễ (offset) trên timeline
        start_us = int(start_sec * 1_000_000) + timeline_offset_us
        duration_us = int((end_sec - start_sec) * 1_000_000)
        
        if duration_us <= 0:
            continue
            
        # Tạo UUID duy nhất cho text material và segment
        text_material_id = str(uuid.uuid4()).upper()
        segment_uuid = str(uuid.uuid4()).upper()
        
        # Cấu trúc nội dung JSON-in-JSON chuẩn của CapCut PC 9.x
        content_obj = {
            "styles": [
                {
                    "fill": {
                        "alpha": 1.0,
                        "content": {
                            "render_type": "solid",
                            "solid": {
                                "color": [1.0, 1.0, 1.0]
                            }
                        }
                    },
                    "font": {
                        "id": "",
                        "path": font_path
                    },
                    "range": [0, len(text_content_wrapped)],
                    "size": 15.0,
                    "useLetterColor": True
                }
            ],
            "text": text_content_wrapped
        }
        content_json_str = json.dumps(content_obj, ensure_ascii=False)
        
        if group_subtitles:
            # === CHỨC NĂNG 1: PHỤ ĐỀ (CÓ nút "Áp dụng cho tất cả" trong CapCut) ===
            text_material = {
                "add_type": 1,
                "alignment": 1,
                "base_content": content_json_str,
                "border_alpha": 1.0,
                "border_color": "#000000",
                "border_width": 0.0,
                "caption_template_info": {
                    "category_id": "",
                    "category_name": "",
                    "effect_id": "",
                    "is_new": False,
                    "path": "",
                    "request_id": "",
                    "resource_id": "",
                    "resource_name": "",
                    "third_resource_id": ""
                },
                "check_flag": 7,
                "combo_info": {"text_templates": []},
                "content": content_json_str,
                "font_category_id": "",
                "font_category_name": "",
                "font_id": "",
                "font_name": "",
                "font_path": font_path,
                "font_resource_id": "",
                "font_size": 15.0,
                "font_title": "none",
                "font_url": "",
                "fonts": [],
                "global_alpha": 1.0,
                "group_id": shared_group_id,
                "has_shadow": False,
                "id": text_material_id,
                "initial_scale": 1.0,
                "is_rich_text": False,
                "line_feed": 1,
                "line_spacing": 0.02,
                "name": "",
                "operation_type": 0,
                "recognize_model": "",
                "recognize_task_id": "",
                "recognize_text": text_content_wrapped,
                "recognize_type": 0,
                "style_name": "",
                "sub_type": 0,
                "subtitle_id": text_material_id,
                "text_alpha": 1.0,
                "text_color": "#FFFFFF",
                "text_size": 30,
                "type": "subtitle",
                "typesetting": 0,
                "use_effect_default_color": False
            }
            
            track_segment = {
                "id": segment_uuid,
                "material_id": text_material_id,
                "target_timerange": {
                    "duration": duration_us,
                    "start": start_us
                },
                "source_timerange": None,
                "render_index": 14000 + i,
                "clip": {
                    "scale": {"x": 1.0, "y": 1.0},
                    "rotation": 0.0,
                    "transform": {"x": 0.0, "y": -0.65},
                    "flip": {"vertical": False, "horizontal": False},
                    "alpha": 1.0
                },
                "sub_type": 0,
                "caption_template_info": {
                    "category_id": "",
                    "category_name": "",
                    "effect_id": "",
                    "is_new": False,
                    "resource_id": ""
                }
            }
        else:
            # === CHỨC NĂNG 2: VĂN BẢN ĐỘC LẬP (KHÔNG CÓ "Áp dụng cho tất cả") ===
            text_material = {
                "add_type": 0,
                "alignment": 1,
                "base_content": content_json_str,
                "border_alpha": 1.0,
                "border_color": "#000000",
                "border_width": 0.0,
                "caption_template_info": {
                    "category_id": "",
                    "category_name": "",
                    "effect_id": "",
                    "is_new": False,
                    "path": "",
                    "request_id": "",
                    "resource_id": "",
                    "resource_name": "",
                    "third_resource_id": ""
                },
                "check_flag": 7,
                "combo_info": {"text_templates": []},
                "content": content_json_str,
                "font_category_id": "",
                "font_category_name": "",
                "font_id": "",
                "font_name": "",
                "font_path": font_path,
                "font_resource_id": "",
                "font_size": 15.0,
                "font_title": "none",
                "font_url": "",
                "fonts": [],
                "global_alpha": 1.0,
                "group_id": "",
                "has_shadow": False,
                "id": text_material_id,
                "initial_scale": 1.0,
                "is_rich_text": False,
                "line_feed": 1,
                "line_spacing": 0.02,
                "name": "",
                "operation_type": 0,
                "recognize_model": "",
                "recognize_task_id": "",
                "recognize_text": text_content_wrapped,
                "recognize_type": 0,
                "style_name": "",
                "sub_type": 0,
                "text_alpha": 1.0,
                "text_color": "#FFFFFF",
                "text_size": 30,
                "type": "text",
                "typesetting": 0,
                "use_effect_default_color": False
            }
            
            track_segment = {
                "id": segment_uuid,
                "material_id": text_material_id,
                "target_timerange": {
                    "duration": duration_us,
                    "start": start_us
                },
                "source_timerange": None,
                "render_index": 14000 + i,
                "clip": {
                    "scale": {"x": 1.0, "y": 1.0},
                    "rotation": 0.0,
                    "transform": {"x": 0.0, "y": -0.65},
                    "flip": {"vertical": False, "horizontal": False},
                    "alpha": 1.0
                },
                "sub_type": 0,
                "caption_template_info": {
                    "category_id": "",
                    "category_name": "",
                    "effect_id": "",
                    "is_new": False,
                    "resource_id": ""
                }
            }
        
        if i < preview_limit:
            log_callback(f"  [Preview Segment {i+1}] {start_sec:.2f}s -> {end_sec:.2f}s: \"{text_content}\"")
        elif i == preview_limit:
            log_callback(f"  ... và {len(segments) - preview_limit} đoạn văn bản khác.")
            
        if not dry_run:
            draft_data["materials"]["texts"].append(text_material)
            text_track["segments"].append(track_segment)
            
        inserted_count += 1
        
    if dry_run:
        log_callback(f"[DRY-RUN] Đã chạy thử nghiệm thành công. KHÔNG lưu thay đổi vào dự án (Tổng số đoạn: {inserted_count}).")
    else:
        # Sao lưu file trước khi ghi đè
        backup_path = draft_content_path + ".bak"
        log_callback(f"Đang sao lưu file cấu trúc cũ sang: {os.path.basename(backup_path)}")
        shutil.copy2(draft_content_path, backup_path)
        
        log_callback("Đang ghi đè dữ liệu mới vào draft_content.json...")
        with open(draft_content_path, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, ensure_ascii=False)
            
        log_callback(f"Hoàn tất lưu trữ! Đã chèn {inserted_count} đoạn phụ đề vào dự án.")
        log_callback("LƯU Ý: Cấu trúc JSON có thể thay đổi tùy thuộc phiên bản CapCut của bạn. Hãy đối chiếu với dự án 'capcut-cli' nếu cần thiết.")
        
    return inserted_count


# ==========================================
# PART 2: GRAPHICAL USER INTERFACE (Tkinter)
# ==========================================

class CapCutAudioToTextApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("CapCut Audio to Text Tool")
        self.geometry("1000x760")
        self.minsize(900, 700)
        
        # Cấu hình màu sắc giao diện Dark Mode cao cấp
        self.bg_main = "#1E1E2E"       # Nền chính tối
        self.bg_frame = "#252538"      # Nền của LabelFrame/Khối
        self.fg_main = "#CDD6F4"       # Màu chữ sáng
        self.fg_dim = "#A6ADC8"        # Màu chữ mờ phụ
        self.accent_color = "#89B4FA"   # Màu xanh dương làm điểm nhấn
        self.btn_bg = "#313244"        # Màu nền nút
        
        self.configure(bg=self.bg_main)
        
        # Tải cấu hình đã lưu
        self.config = self._load_config()
        
        # Biến lưu trữ dữ liệu từ cấu hình hoặc giá trị mặc định
        self.var_drafts_dir = tk.StringVar(value=self.config.get("drafts_dir", ""))
        self.var_language = tk.StringVar(value=self.config.get("language", "Tự động nhận diện"))
        self.var_model = tk.StringVar(value=self.config.get("model", "small"))
        self.var_dry_run = tk.BooleanVar(value=self.config.get("dry_run", False))
        self.var_max_words = tk.IntVar(value=self.config.get("max_words", 13))
        
        # Bản đồ ngôn ngữ sang mã whisper
        self.lang_map = {
            "Tự động nhận diện": None,
            "Tiếng Việt (vi)": "vi",
            "Tiếng Anh (en)": "en",
            "Tiếng Trung (zh)": "zh",
            "Tiếng Hàn (ko)": "ko",
            "Tiếng Nhật (ja)": "ja"
        }
        
        self._init_styles()
        self._create_widgets()
        
        # Theo dõi sự thay đổi của thư mục Drafts để tự động lưu và quét dự án
        self.var_drafts_dir.trace_add("write", lambda *args: self._on_drafts_dir_change())
        
        # Bắt sự kiện đóng cửa sổ để lưu cấu hình
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Tự động quét dự án khi mở app nếu đã có đường dẫn từ trước
        if self.var_drafts_dir.get():
            self.after(500, self._refresh_draft_list)
        
    def _init_styles(self):
        # Thiết lập style cho các widget ttk
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        # Cấu hình Treeview
        self.style.configure("Treeview", 
                             background=self.bg_frame, 
                             foreground=self.fg_main, 
                             fieldbackground=self.bg_frame,
                             rowheight=25,
                             font=("Segoe UI", 10))
        self.style.map("Treeview", background=[("selected", self.accent_color)], foreground=[("selected", "#1E1E2E")])
        self.style.configure("Treeview.Heading", 
                             background=self.btn_bg, 
                             foreground=self.fg_main, 
                             font=("Segoe UI", 10, "bold"),
                             borderwidth=1)
        
        # Cấu hình LabelFrame
        self.style.configure("TLabelframe", background=self.bg_main, foreground=self.accent_color, font=("Segoe UI", 11, "bold"))
        self.style.configure("TLabelframe.Label", background=self.bg_main, foreground=self.accent_color)

    def _create_widgets(self):
        # 1. Tiêu đề ứng dụng
        title_label = tk.Label(self, text="CAPCUT AUDIO TO TEXT TOOL", font=("Segoe UI", 18, "bold"), 
                               bg=self.bg_main, fg=self.accent_color, pady=10)
        title_label.pack(fill=tk.X)
        
        # Khung chính chia 2 phần: Trên (Cài đặt + Danh sách) và Dưới (Log)
        main_paned = tk.PanedWindow(self, orient=tk.VERTICAL, bg=self.bg_main, bd=0, sashwidth=4, sashrelief=tk.FLAT)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # Khung chứa các phần cấu hình ở phía trên
        top_frame = tk.Frame(main_paned, bg=self.bg_main)
        main_paned.add(top_frame, minsize=400)
        
        # Layout 2 cột cho phần trên: Cột trái (Đường dẫn + Tùy chọn) và Cột phải (Danh sách dự án)
        top_left_frame = tk.Frame(top_frame, bg=self.bg_main)
        top_left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        top_right_frame = tk.Frame(top_frame, bg=self.bg_main)
        top_right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # --- CỘT TRÁI ---
        # A. Khối "Đường dẫn hệ thống"
        lf_paths = tk.LabelFrame(top_left_frame, text="Đường dẫn hệ thống", bg=self.bg_frame, fg=self.accent_color,
                                  font=("Segoe UI", 11, "bold"), padx=10, pady=10, bd=1, relief=tk.SOLID)
        lf_paths.pack(fill=tk.X, pady=(0, 10))
        
        # Thư mục Drafts CapCut
        tk.Label(lf_paths, text="Thư mục Drafts CapCut:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        entry_drafts = tk.Entry(lf_paths, textvariable=self.var_drafts_dir, bg=self.bg_main, fg=self.fg_main, insertbackground=self.fg_main, bd=1, relief=tk.SOLID, font=("Segoe UI", 10))
        entry_drafts.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        btn_browse_drafts = tk.Button(lf_paths, text="Browse...", bg=self.btn_bg, fg=self.fg_main, activebackground=self.accent_color, activeforeground=self.bg_main, bd=0, padx=8, font=("Segoe UI", 9), command=self._browse_drafts_dir)
        btn_browse_drafts.grid(row=0, column=2, pady=5)
        
        lf_paths.columnconfigure(1, weight=1)
        
        # B. Khối "Tùy chọn chuyển đổi"
        lf_options = tk.LabelFrame(top_left_frame, text="Tùy chọn chuyển đổi", bg=self.bg_frame, fg=self.accent_color,
                                    font=("Segoe UI", 11, "bold"), padx=10, pady=10, bd=1, relief=tk.SOLID)
        lf_options.pack(fill=tk.BOTH, expand=True)
        
        # Ngôn ngữ voice
        tk.Label(lf_options, text="Ngôn ngữ voice:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W, pady=8)
        cb_lang = ttk.Combobox(lf_options, textvariable=self.var_language, values=list(self.lang_map.keys()), state="readonly", font=("Segoe UI", 10))
        cb_lang.grid(row=0, column=1, sticky=tk.W, padx=10, pady=8)
        
        # Model Whisper
        tk.Label(lf_options, text="Model Whisper:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 10)).grid(row=1, column=0, sticky=tk.W, pady=8)
        cb_model = ttk.Combobox(lf_options, textvariable=self.var_model, values=["tiny", "base", "small", "medium", "large"], state="readonly", font=("Segoe UI", 10))
        cb_model.grid(row=1, column=1, sticky=tk.W, padx=10, pady=8)
        btn_save_model = tk.Button(lf_options, text="Lưu mặc định", bg=self.btn_bg, fg=self.fg_main, activebackground=self.accent_color, activeforeground=self.bg_main, bd=0, padx=8, font=("Segoe UI", 9), command=self._save_model_default)
        btn_save_model.grid(row=1, column=2, padx=10, pady=8)
        
        # Giới hạn số từ
        tk.Label(lf_options, text="Giới hạn từ/đoạn:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 10)).grid(row=2, column=0, sticky=tk.W, pady=8)
        sb_words = tk.Spinbox(lf_options, from_=1, to=100, textvariable=self.var_max_words, width=8, bg=self.bg_main, fg=self.fg_main, insertbackground=self.fg_main, bd=1, relief=tk.SOLID, font=("Segoe UI", 10))
        sb_words.grid(row=2, column=1, sticky=tk.W, padx=10, pady=8)
        
        # Checkbox Dry Run
        chk_dry = tk.Checkbutton(lf_options, text="Chạy thử nghiệm (Dry-Run)", variable=self.var_dry_run, 
                                 bg=self.bg_frame, fg=self.fg_main, activebackground=self.bg_frame, activeforeground=self.fg_main,
                                 selectcolor=self.bg_main, font=("Segoe UI", 10))
        chk_dry.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=10)
        
        # Nút hành động lớn 1: Gom nhóm (Áp dụng cho tất cả)
        self.btn_convert = tk.Button(lf_options, text="CHUYỂN ĐỔI VOICE → TEXT (NHÓM SUB)", bg=self.accent_color, fg="#1E1E2E",
                                     activebackground="#b4befe", activeforeground="#1E1E2E", font=("Segoe UI", 11, "bold"),
                                     bd=0, height=2, width=32, cursor="hand2", command=lambda: self._start_conversion_thread(group_subtitles=True))
        self.btn_convert.grid(row=4, column=0, columnspan=2, pady=(15, 5), sticky=tk.N)
        
        # Nút hành động lớn 2: Không gom nhóm (Không hiện áp dụng cho tất cả)
        self.btn_convert_nogroup = tk.Button(lf_options, text="CHUYỂN ĐỔI (KHÔNG ÁP DỤNG TẤT CẢ)", bg="#fab387", fg="#1E1E2E",
                                             activebackground="#f9e2af", activeforeground="#1E1E2E", font=("Segoe UI", 11, "bold"),
                                             bd=0, height=2, width=32, cursor="hand2", command=lambda: self._start_conversion_thread(group_subtitles=False))
        self.btn_convert_nogroup.grid(row=5, column=0, columnspan=2, pady=(5, 15), sticky=tk.N)
        
        # --- CỘT PHẢI ---
        # Khối "Danh sách dự án (Drafts)"
        lf_drafts = tk.LabelFrame(top_right_frame, text="Danh sách dự án (Drafts)", bg=self.bg_frame, fg=self.accent_color,
                                   font=("Segoe UI", 11, "bold"), padx=10, pady=10, bd=1, relief=tk.SOLID)
        lf_drafts.pack(fill=tk.BOTH, expand=True)
        
        # Khung trên chứa nút Làm mới và nhãn hướng dẫn
        header_drafts = tk.Frame(lf_drafts, bg=self.bg_frame)
        header_drafts.pack(fill=tk.X, pady=(0, 8))
        
        lbl_drafts_info = tk.Label(header_drafts, text="Dự án khả dụng:", bg=self.bg_frame, fg=self.fg_dim, font=("Segoe UI", 9, "italic"))
        lbl_drafts_info.pack(side=tk.LEFT, anchor=tk.CENTER)
        
        btn_refresh = tk.Button(header_drafts, text="Làm mới (Refresh)", bg=self.btn_bg, fg=self.fg_main,
                                activebackground=self.accent_color, activeforeground=self.bg_main,
                                bd=0, padx=12, pady=4, font=("Segoe UI", 9, "bold"), command=self._refresh_draft_list)
        btn_refresh.pack(side=tk.RIGHT, anchor=tk.CENTER)
        
        # Khung chứa Treeview
        tree_container = tk.Frame(lf_drafts, bg=self.bg_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        # Treeview danh sách
        cols = ("name", "status")
        self.tree_drafts = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="browse")
        self.tree_drafts.heading("name", text="Tên dự án (Draft Name)")
        self.tree_drafts.heading("status", text="Trạng thái (Status)")
        self.tree_drafts.column("name", width=250, anchor=tk.W)
        self.tree_drafts.column("status", width=120, anchor=tk.CENTER)
        
        # Scrollbar cho Treeview
        tree_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree_drafts.yview)
        self.tree_drafts.configure(yscrollcommand=tree_scroll.set)
        
        self.tree_drafts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # --- KHỐI DƯỚI CÙNG (OUTPUT LOG) ---
        log_frame = tk.LabelFrame(main_paned, text="Output Log", bg=self.bg_frame, fg=self.accent_color,
                                  font=("Segoe UI", 11, "bold"), padx=10, pady=10, bd=1, relief=tk.SOLID)
        main_paned.add(log_frame, minsize=200)
        
        self.txt_log = tk.Text(log_frame, bg=self.bg_main, fg=self.fg_main, insertbackground=self.fg_main,
                               wrap=tk.WORD, font=("Consolas", 10), state=tk.DISABLED, bd=0)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scrollbar.set)
        
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Ghi log chào mừng ban đầu
        self.log("Ứng dụng CapCut Audio to Text Tool đã sẵn sàng.")
        self.log("Cách dùng: Chọn thư mục Drafts, chọn một dự án trong danh sách và nhấn 'CHUYỂN ĐỔI VOICE → TEXT'")
        
    # --- CÁC HÀM XỬ LÝ SỰ KIỆN GIAO DIỆN ---
    def log(self, message):
        """Ghi thông tin kèm timestamp vào Output Log một cách an toàn."""
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
        self.txt_log.configure(state=tk.NORMAL)
        self.txt_log.insert(tk.END, f"{timestamp} {message}\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state=tk.DISABLED)

    def _load_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        default_config = {
            "drafts_dir": get_default_drafts_dir(),
            "language": "Tự động nhận diện",
            "model": "small",
            "dry_run": False,
            "max_words": 13
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    default_config.update(saved)
            except:
                pass
        # Nếu drafts_dir trong config đang rỗng, thử dò tìm tự động
        if not default_config.get("drafts_dir"):
            default_config["drafts_dir"] = get_default_drafts_dir()
        return default_config

    def _save_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        try:
            config_data = {
                "drafts_dir": self.var_drafts_dir.get(),
                "language": self.var_language.get(),
                "model": self.var_model.get(),
                "dry_run": self.var_dry_run.get(),
                "max_words": int(self.var_max_words.get())
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            pass

    def _on_close(self):
        self._save_config()
        self.destroy()

    def _save_model_default(self):
        self._save_config()
        self.log(f"Đã lưu model mặc định: '{self.var_model.get()}'")
        messagebox.showinfo("Thành công", f"Đã lưu cấu hình (Model: '{self.var_model.get()}') làm mặc định cho các lần khởi chạy sau!")

    def _on_drafts_dir_change(self):
        self._save_config()
        path = self.var_drafts_dir.get()
        if path and os.path.exists(path):
            self._refresh_draft_list()

    def _browse_drafts_dir(self):
        path = filedialog.askdirectory(title="Chọn thư mục chứa các dự án (Drafts) của CapCut")
        if path:
            self.var_drafts_dir.set(path)
            self.log(f"Đã chọn thư mục Drafts: {path}")

    def _refresh_draft_list(self):
        # Xóa danh sách cũ
        for item in self.tree_drafts.get_children():
            self.tree_drafts.delete(item)
            
        drafts_root = self.var_drafts_dir.get()
        if not drafts_root:
            return
            
        self.log("Đang quét danh sách dự án...")
        drafts = find_drafts(drafts_root)
        for d in drafts:
            self.tree_drafts.insert("", tk.END, values=(d["name"], d["status"]), tags=(d["path"],))
        self.log(f"Đã quét xong. Tìm thấy {len(drafts)} dự án.")

    def _is_capcut_running(self):
        import subprocess
        try:
            output = subprocess.check_output('tasklist', shell=True).decode('utf-8', errors='ignore').lower()
            return "capcut" in output
        except:
            return False

    def _start_conversion_thread(self, group_subtitles=True):
        selected_project_path = ""
        
        selected_item = self.tree_drafts.selection()
        if selected_item:
            # Lấy đường dẫn lưu trong tags
            tags = self.tree_drafts.item(selected_item[0], "tags")
            if tags:
                selected_project_path = tags[0]
                
        if not selected_project_path:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một dự án trong danh sách!")
            return
            
        # Kiểm tra xem CapCut có đang mở không để cảnh báo người dùng
        if self._is_capcut_running():
            proceed = messagebox.askokcancel(
                "Lưu ý quan trọng",
                "Phần mềm CapCut hiện tại đang hoạt động.\n\n"
                "QUAN TRỌNG: Bạn CẦN thoát dự án đang chỉnh sửa ra ngoài màn hình Trang chủ (Homepage) của CapCut hoặc đóng hẳn CapCut trước khi tiếp tục.\n"
                "Nếu vẫn để mở màn hình chỉnh sửa dự án này, CapCut sẽ tự động ghi đè và làm MẤT HOÀN TOÀN phụ đề mới.\n\n"
                "Bạn đã quay ra Trang chủ và muốn tiếp tục?"
            )
            if not proceed:
                return
                
        # Vô hiệu hóa cả hai nút để tránh double click
        self.btn_convert.configure(state=tk.DISABLED, text="ĐANG XỬ LÝ...")
        self.btn_convert_nogroup.configure(state=tk.DISABLED, text="ĐANG XỬ LÝ...")
        
        # Khởi chạy tiểu trình xử lý
        t = threading.Thread(target=self._process_conversion, args=(selected_project_path, group_subtitles))
        t.daemon = True
        t.start()

    def _process_conversion(self, project_path, group_subtitles=True):
        language_display = self.var_language.get()
        language_code = self.lang_map[language_display]
        model_size = self.var_model.get()
        dry_run = self.var_dry_run.get()
        max_words = self.var_max_words.get()
        
        # Lưu cấu hình mỗi khi bắt đầu tiến hành convert
        self._save_config()
        
        self.log("-" * 50)
        self.log(f"KHỞI ĐỘNG CHUYỂN ĐỔI DỰ ÁN:")
        self.log(f"  Dự án đích: {project_path}")
        self.log(f"  Model Whisper: {model_size}")
        self.log(f"  Giới hạn từ: {max_words} từ / đoạn")
        self.log(f"  Chế độ: {'Chạy thử nghiệm (Dry-Run)' if dry_run else 'Ghi trực tiếp dự án'}")
        
        try:
            # Tự động tìm danh sách các file audio/video ứng viên
            candidates = find_audio_candidates(project_path)
            if not candidates:
                raise FileNotFoundError("Không tìm thấy bất kỳ file audio/video nào (.mp3, .wav, .m4a, .mp4, .aac) trong thư mục dự án!")
            
            segments = None
            last_error = None
            successful_audio_path = None
            successful_offset_us = 0
            
            for item in candidates:
                audio_path = item["path"]
                offset_us = item["offset_us"]
                self.log(f"Thử nghiệm nhận diện file: {os.path.basename(audio_path)}")
                try:
                    # Bước 1: Gọi Whisper để Transcribe
                    candidate_segments = transcribe_audio(audio_path, language_code, model_size, self.log)
                    # Nếu tìm thấy ít nhất 1 đoạn chữ hoặc đây là file cuối cùng trong danh sách
                    if candidate_segments or item == candidates[-1]:
                        segments = candidate_segments
                        successful_audio_path = audio_path
                        successful_offset_us = offset_us
                        if candidate_segments:
                            break # Đã tìm thấy file có giọng nói, dừng tìm kiếm
                        else:
                            self.log(f"[THÔNG TIN] File {os.path.basename(audio_path)} thành công nhưng không chứa giọng nói (0 đoạn).")
                    else:
                        self.log(f"[THÔNG TIN] Bỏ qua file {os.path.basename(audio_path)} do không phát hiện giọng nói (0 đoạn), đang thử tiếp file khác...")
                except Exception as ex:
                    last_error = ex
                    self.log(f"[CẢNH BÁO] Bỏ qua file do lỗi âm thanh (có thể file không có stream audio): {os.path.basename(audio_path)}")
            
            if segments is None:
                raise RuntimeError(f"Tất cả các file audio/video được tìm thấy đều không có âm thanh hoặc không thể xử lý. Lỗi chi tiết cuối cùng: {last_error}")
            
            # Tự động chia nhỏ các câu phụ đề quá dài (tối đa max_words từ mỗi đoạn)
            segments = split_segments_by_words(segments, max_words=max_words)
            
            # Bước 2: Chèn text vào draft
            inserted = insert_text_into_draft(project_path, segments, dry_run, self.log, timeline_offset_us=successful_offset_us, group_subtitles=group_subtitles)
            
            mode_text = " (Chạy thử nghiệm)" if dry_run else ""
            messagebox.showinfo("Thành công", f"Đã hoàn thành chuyển đổi{mode_text}!\nĐã xử lý {inserted} đoạn văn bản từ file {os.path.basename(successful_audio_path)}.")
            
        except Exception as e:
            self.log(f"[THẤT BẠI] Quá trình xử lý bị dừng do lỗi: {e}")
            messagebox.showerror("Lỗi xử lý", f"Đã xảy ra lỗi trong quá trình chuyển đổi:\n{e}")
            
        finally:
            self.btn_convert.configure(state=tk.NORMAL, text="CHUYỂN ĐỔI VOICE → TEXT (NHÓM SUB)")
            self.btn_convert_nogroup.configure(state=tk.NORMAL, text="CHUYỂN ĐỔI (KHÔNG ÁP DỤNG TẤT CẢ)")
            self.log("-" * 50)
            
if __name__ == "__main__":
    app = CapCutAudioToTextApp()
    app.mainloop()
