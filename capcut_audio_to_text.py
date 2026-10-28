import os
import sys
import json
import uuid
import shutil
import datetime
import threading
import time
import base64
import tempfile
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ==========================================
# THIẾT LẬP MÔI TRƯỜNG & ĐƯỜNG DẪN HỆ THỐNG
# ==========================================

def setup_ffmpeg_path():
    """
    Tự động dò tìm và nạp đường dẫn FFmpeg vào PATH để Whisper và nén âm thanh sử dụng được
    ngay cả khi người dùng chưa cấu hình biến môi trường thủ công.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Kiểm tra trong thư mục hiện tại hoặc thư mục con ffmpeg / CapCut_STT_Tool
    candidates = [
        current_dir,
        os.path.join(current_dir, "CapCut_STT_Tool"),
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
# PART 1: PROCESSING LOGIC & COLAB CLIENT
# ==========================================

def check_colab_health(colab_url):
    """
    Kiểm tra trạng thái kết nối tới Google Colab GPU Server.
    Trả về (True/False, chuỗi thông báo kết quả/thông số GPU).
    """
    if not colab_url or not colab_url.startswith("http"):
        return False, "Link Colab không hợp lệ (cần bắt đầu bằng https://)"
        
    url = f"{colab_url.rstrip('/')}/health"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CapCutSTTTool/1.0"})
        with urllib.request.urlopen(req, timeout=7) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                gpu = data.get("gpu_name", "GPU")
                vram_free = data.get("vram_free_gb", 0)
                vram_total = data.get("vram_total_gb", 0)
                model_name = data.get("model", "Whisper Large-v3")
                return True, f"ĐÃ KẾT NỐI: {gpu} (Trống {vram_free}GB / {vram_total}GB VRAM) - {model_name}"
            return False, f"Server phản hồi mã lỗi: {resp.status}"
    except Exception as e:
        return False, f"Không thể kết nối Colab: {e}"

def compress_audio_for_colab(audio_path, log_callback):
    """
    Nén nhanh file âm thanh hoặc video sang chuẩn Mono 16kHz FLAC Lossless bằng FFmpeg nội bộ.
    Giúp giảm dung lượng file đến 80-90% để việc tải lên Cloudflare Colab diễn ra chỉ trong 1-3 giây.
    """
    setup_ffmpeg_path()
    ffmpeg_exe = shutil.which("ffmpeg")
    
    temp_dir = tempfile.gettempdir()
    flac_out = os.path.join(temp_dir, f"capcut_stt_{uuid.uuid4().hex[:8]}.flac")
    
    if ffmpeg_exe:
        log_callback("Đang trích xuất & nén audio chuẩn 16kHz Mono FLAC siêu tốc để tải lên Colab...")
        cmd = [
            ffmpeg_exe, "-y",
            "-i", audio_path,
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "flac",
            flac_out
        ]
        try:
            import subprocess
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(flac_out) and os.path.getsize(flac_out) > 0:
                orig_mb = os.path.getsize(audio_path) / (1024 * 1024)
                flac_mb = os.path.getsize(flac_out) / (1024 * 1024)
                log_callback(f"  -> Nén thành công: {orig_mb:.1f} MB -> {flac_mb:.1f} MB (Giảm {(1 - flac_mb/max(orig_mb,0.001))*100:.0f}% dung lượng)")
                with open(flac_out, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                try:
                    os.remove(flac_out)
                except Exception:
                    pass
                return b64_data, "flac"
        except Exception as e:
            log_callback(f"[Cảnh báo] Lỗi khi nén bằng FFmpeg: {e}. Đang đọc trực tiếp file gốc...")

    # Fallback: Đọc trực tiếp file gốc nếu FFmpeg gặp sự cố
    with open(audio_path, "rb") as f:
        ext = os.path.splitext(audio_path)[1].replace(".", "").lower() or "wav"
        return base64.b64encode(f.read()).decode("utf-8"), ext

def transcribe_audio_colab(colab_url, audio_path, language_code, log_callback):
    """
    Gửi file âm thanh lên Google Colab GPU Server để xử lý bằng Whisper Large-v3 Batched.
    Sử dụng Async Task Queue để chống nghẽn và chống Cloudflare Gateway Timeout.
    """
    b64_audio, audio_ext = compress_audio_for_colab(audio_path, log_callback)
    
    submit_url = f"{colab_url.rstrip('/')}/submit_transcribe"
    payload = json.dumps({
        "audio_base64": b64_audio,
        "audio_ext": audio_ext,
        "language": language_code or "vi",
        "batch_size": 24, # Khai thác tối ưu 13.0 - 13.5 GB VRAM trên Tesla T4
        "beam_size": 5,    # SOTA accuracy tiếng Việt
        "vad_filter": True # Chống lặp từ / ảo giác
    }).encode("utf-8")
    
    log_callback("Đang tải dữ liệu âm thanh lên Google Colab GPU (Tesla T4 16GB)...")
    req = urllib.request.Request(
        submit_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CapCutSTTTool/1.0"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            res = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log_callback(f"[LỖI GỬI DỮ LIỆU] Không thể gửi âm thanh tới Colab: {e}")
        raise RuntimeError(f"Lỗi kết nối Colab: {e}")
        
    task_id = res.get("task_id")
    if not task_id:
        raise RuntimeError(f"Server Colab không trả về task_id hợp lệ: {res}")
        
    log_callback(f"Dữ liệu đã vào hàng đợi GPU Colab! Mã tác vụ: {task_id[:8]}...")
    log_callback("Tesla T4 đang chạy Batched Whisper Large-v3 (Mức VRAM tối ưu ~13.5GB)...")
    
    status_url = f"{colab_url.rstrip('/')}/task_status/{task_id}"
    start_time = time.time()
    
    # Polling chờ kết quả
    while True:
        time.sleep(1.5)
        try:
            poll_req = urllib.request.Request(status_url, headers={"User-Agent": "CapCutSTTTool/1.0"})
            with urllib.request.urlopen(poll_req, timeout=15) as poll_resp:
                status_data = json.loads(poll_resp.read().decode("utf-8"))
        except Exception:
            continue
            
        status = status_data.get("status")
        if status == "completed":
            result = status_data.get("result", {})
            proc_time = result.get("processing_time_sec", round(time.time() - start_time, 2))
            segments = result.get("segments", [])
            log_callback(f"--> [HOÀN TẤT TRÊN COLAB] GPU T4 xử lý xong trong {proc_time}s! Nhận diện {len(segments)} đoạn phụ đề.")
            
            # Dọn dẹp task trên Colab
            try:
                clear_req = urllib.request.Request(
                    f"{colab_url.rstrip('/')}/task_clear/{task_id}",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(clear_req, timeout=5)
            except Exception:
                pass
                
            return segments
        elif status == "failed":
            err_msg = status_data.get("error", "Lỗi không xác định trên Colab")
            log_callback(f"[LỖI XỬ LÝ COLAB] {err_msg}")
            raise RuntimeError(f"Colab GPU báo lỗi: {err_msg}")
        else:
            elapsed = int(time.time() - start_time)
            if elapsed % 6 == 0 and elapsed > 0:
                log_callback(f"  ... Tesla T4 đang giải mã song song ({elapsed}s trôi qua)...")

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
    supported_exts = ('.mp3', '.wav', '.m4a', '.mp4', '.aac', '.flac')
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
                            target_range = segment.get("target_timerange", {})
                            source_range = segment.get("source_timerange") or {}
                            target_start = target_range.get("start", 0)
                            source_start = source_range.get("start", 0) if source_range else 0
                            offset_us = target_start - source_start
                            
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
                                
        candidates = audio_candidates + video_candidates
    except Exception:
        pass
        
    return candidates

_MODEL_CACHE = {}

def transcribe_audio_local(audio_path, language, model_size, log_callback):
    """
    Gọi Whisper Local trên máy cá nhân để chuyển đổi file audio sang văn bản.
    """
    log_callback(f"Bắt đầu quá trình nhận diện giọng nói (Local Offline): {os.path.basename(audio_path)}")
    log_callback("Kiểm tra thư viện Whisper local...")
    
    try:
        import whisper
    except ImportError:
        log_callback("[LỖI THIẾU THƯ VIỆN] Không tìm thấy thư viện 'openai-whisper'.")
        log_callback("Vui lòng cài đặt bằng lệnh: pip install openai-whisper")
        raise ImportError("Thư viện 'openai-whisper' chưa được cài đặt.")
        
    global _MODEL_CACHE
    
    setup_ffmpeg_path()
    if not shutil.which("ffmpeg"):
        log_callback("[CẢNH BÁO] Không tìm thấy FFmpeg trong hệ thống!")
    
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log_callback(f"Thiết bị phần cứng Local: {device.upper()}")
    
    user_home = os.path.expanduser("~")
    model_file_path = os.path.join(user_home, ".cache", "whisper", f"{model_size}.pt")
    is_downloaded = os.path.exists(model_file_path)
    
    other_models = [m for m in list(_MODEL_CACHE.keys()) if m != model_size]
    for m in other_models:
        del _MODEL_CACHE[m]
        
    if model_size in _MODEL_CACHE:
        log_callback(f"Đã sử dụng model Whisper '{model_size}' sẵn có trong RAM.")
        model = _MODEL_CACHE[model_size]
    else:
        if is_downloaded:
            log_callback(f"Đang nạp model Whisper '{model_size}' từ máy...")
        else:
            log_callback(f"Đang tải model Whisper '{model_size}' (chỉ tải ở lần đầu)...")
            
        try:
            model = whisper.load_model(model_size, device=device)
            _MODEL_CACHE[model_size] = model
        except Exception as e:
            log_callback(f"[LỖI TẢI MODEL] Không thể tải model Whisper '{model_size}': {e}")
            raise e
        
    log_callback("Đang xử lý chuyển đổi audio thành văn bản...")
    kwargs = {
        "fp16": (device == "cuda"),
        "beam_size": 1,
        "best_of": 1
    }
    
    if language:
        kwargs["language"] = language
        log_callback(f"Ngôn ngữ được chỉ định: {language}")
    else:
        log_callback("Đang tự động nhận diện ngôn ngữ voice...")
        
    try:
        torch.set_num_threads(4)
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
    """
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        word_len = len(word)
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
    Bảo vệ ranh giới dấu câu và không cắt đôi từ ghép tiếng Việt có nghĩa.
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
        num_chunks = math.ceil(total_words / max_words)
        base_chunk_size = total_words // num_chunks
        remainder = total_words % num_chunks
        
        chunk_sizes = []
        for i in range(num_chunks):
            size = base_chunk_size + (1 if i < remainder else 0)
            chunk_sizes.append(size)
            
        split_indices = []
        curr_idx = 0
        for size in chunk_sizes[:-1]:
            curr_idx += size
            split_indices.append(curr_idx)
            
        # 1. Ưu tiên ngắt tại dấu câu
        for i in range(len(split_indices)):
            split_idx = split_indices[i]
            prev_split = split_indices[i - 1] if i > 0 else 0
            next_split = split_indices[i + 1] if i < len(split_indices) - 1 else total_words
            
            best_adj_idx = None
            min_dist = 999
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

        # 2. Tránh cắt đôi từ ghép tiếng Việt
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
                        
        adjusted_chunk_sizes = []
        prev = 0
        for idx in split_indices:
            adjusted_chunk_sizes.append(idx - prev)
            prev = idx
        adjusted_chunk_sizes.append(total_words - prev)
        chunk_sizes = adjusted_chunk_sizes
            
        current_word_idx = 0
        time_per_word = total_duration / total_words
        
        for size in chunk_sizes:
            chunk_words = words[current_word_idx : current_word_idx + size]
            chunk_text = " ".join(chunk_words)
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
    Tự động tìm đường dẫn font hệ thống mặc định của ứng dụng CapCut trên máy người dùng.
    """
    try:
        user_home = os.path.expanduser("~")
        apps_dir = os.path.join(user_home, "AppData", "Local", "CapCut", "Apps")
        if os.path.exists(apps_dir):
            versions = [d for d in os.listdir(apps_dir) if os.path.isdir(os.path.join(apps_dir, d))]
            if versions:
                versions.sort()
                latest_version = versions[-1]
                font_path = os.path.join(apps_dir, latest_version, "Resources", "Font", "SystemFont", "en.ttf")
                if os.path.exists(font_path):
                    return font_path.replace("\\", "/")
    except Exception:
        pass
    return "C:/Users/baohu/AppData/Local/CapCut/Apps/8.9.1.3802/Resources/Font/SystemFont/en.ttf"

def insert_text_into_draft(project_path, segments, dry_run, log_callback, timeline_offset_us=0, group_subtitles=True):
    """
    Chèn các đoạn văn bản (subtitles) vào draft_content.json của project CapCut.
    """
    draft_content_path = os.path.join(project_path, "draft_content.json")
    if not os.path.exists(draft_content_path):
        raise FileNotFoundError(f"Không tìm thấy file {draft_content_path}")
        
    log_callback(f"Đang đọc cấu trúc dự án: {draft_content_path}")
    with open(draft_content_path, "r", encoding="utf-8") as f:
        draft_data = json.load(f)
            
    if "materials" not in draft_data:
        draft_data["materials"] = {}
    if "texts" not in draft_data["materials"]:
        draft_data["materials"]["texts"] = []
    if "tracks" not in draft_data:
        draft_data["tracks"] = []
        
    log_callback("Tạo track text mới chuyên biệt cho phụ đề...")
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
    shared_group_id = f"vi-VN_{int(time.time() * 1000)}" if group_subtitles else ""
    font_path = get_capcut_font_path()
    
    for i, seg in enumerate(segments):
        start_sec = seg["start"]
        end_sec = seg["end"]
        text_content = seg["text"]
        
        text_content_wrapped = wrap_text(text_content, max_chars=40)
        start_us = int(start_sec * 1_000_000) + timeline_offset_us
        duration_us = int((end_sec - start_sec) * 1_000_000)
        
        if duration_us <= 0:
            continue
            
        text_material_id = str(uuid.uuid4()).upper()
        segment_uuid = str(uuid.uuid4()).upper()
        
        content_obj = {
            "styles": [
                {
                    "fill": {
                        "alpha": 1.0,
                        "content": {
                            "render_type": "solid",
                            "solid": {"color": [1.0, 1.0, 1.0]}
                        }
                    },
                    "font": {"id": "", "path": font_path},
                    "range": [0, len(text_content_wrapped)],
                    "size": 15.0,
                    "useLetterColor": True
                }
            ],
            "text": text_content_wrapped
        }
        content_json_str = json.dumps(content_obj, ensure_ascii=False)
        
        if group_subtitles:
            # Chế độ Gom nhóm phụ đề: Có nút "Áp dụng cho tất cả" trong CapCut
            text_material = {
                "add_type": 1,
                "alignment": 1,
                "base_content": content_json_str,
                "border_alpha": 1.0,
                "border_color": "#000000",
                "border_width": 0.0,
                "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "is_new": False, "path": "", "request_id": "", "resource_id": "", "resource_name": "", "third_resource_id": ""},
                "check_flag": 7,
                "combo_info": {"text_templates": []},
                "content": content_json_str,
                "font_category_id": "", "font_category_name": "", "font_id": "", "font_name": "",
                "font_path": font_path, "font_resource_id": "", "font_size": 15.0, "font_title": "none",
                "font_url": "", "fonts": [], "global_alpha": 1.0, "group_id": shared_group_id, "has_shadow": False,
                "id": text_material_id, "initial_scale": 1.0, "is_rich_text": False, "line_feed": 1, "line_spacing": 0.02,
                "name": "", "operation_type": 0, "recognize_model": "", "recognize_task_id": "",
                "recognize_text": text_content_wrapped, "recognize_type": 0, "style_name": "", "sub_type": 0,
                "subtitle_id": text_material_id, "text_alpha": 1.0, "text_color": "#FFFFFF", "text_size": 30,
                "type": "subtitle", "typesetting": 0, "use_effect_default_color": False
            }
        else:
            # Chế độ Văn bản độc lập
            text_material = {
                "add_type": 0,
                "alignment": 1,
                "base_content": content_json_str,
                "border_alpha": 1.0,
                "border_color": "#000000",
                "border_width": 0.0,
                "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "is_new": False, "path": "", "request_id": "", "resource_id": "", "resource_name": "", "third_resource_id": ""},
                "check_flag": 7,
                "combo_info": {"text_templates": []},
                "content": content_json_str,
                "font_category_id": "", "font_category_name": "", "font_id": "", "font_name": "",
                "font_path": font_path, "font_resource_id": "", "font_size": 15.0, "font_title": "none",
                "font_url": "", "fonts": [], "global_alpha": 1.0, "group_id": "", "has_shadow": False,
                "id": text_material_id, "initial_scale": 1.0, "is_rich_text": False, "line_feed": 1, "line_spacing": 0.02,
                "name": "", "operation_type": 0, "recognize_model": "", "recognize_task_id": "",
                "recognize_text": text_content_wrapped, "recognize_type": 0, "style_name": "", "sub_type": 0,
                "text_alpha": 1.0, "text_color": "#FFFFFF", "text_size": 30, "type": "text",
                "typesetting": 0, "use_effect_default_color": False
            }
            
        track_segment = {
            "id": segment_uuid,
            "material_id": text_material_id,
            "target_timerange": {"duration": duration_us, "start": start_us},
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
            "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "is_new": False, "resource_id": ""}
        }
        
        if i < preview_limit:
            log_callback(f"  [Đoạn {i+1}] {start_sec:.2f}s -> {end_sec:.2f}s: \"{text_content}\"")
        elif i == preview_limit:
            log_callback(f"  ... và {len(segments) - preview_limit} đoạn văn bản khác.")
            
        if not dry_run:
            draft_data["materials"]["texts"].append(text_material)
            text_track["segments"].append(track_segment)
            
        inserted_count += 1
        
    if dry_run:
        log_callback(f"[DRY-RUN] Đã chạy thử nghiệm thành công (KHÔNG ghi đè file, tổng {inserted_count} đoạn).")
    else:
        backup_path = draft_content_path + ".bak"
        log_callback(f"Đang sao lưu file cũ sang: {os.path.basename(backup_path)}")
        shutil.copy2(draft_content_path, backup_path)
        
        log_callback("Đang ghi đè dữ liệu mới vào draft_content.json...")
        with open(draft_content_path, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, ensure_ascii=False)
            
        log_callback(f"Hoàn tất! Đã chèn {inserted_count} đoạn phụ đề vào timeline CapCut.")
        
    return inserted_count


# ==========================================
# PART 2: GRAPHICAL USER INTERFACE (Tkinter)
# ==========================================

class CapCutAudioToTextApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("CapCut Audio to Text Tool - Colab GPU & Local STT")
        self.geometry("1060x820")
        self.minsize(960, 740)
        
        # Cấu hình màu sắc giao diện Dark Mode
        self.bg_main = "#1E1E2E"
        self.bg_frame = "#252538"
        self.fg_main = "#CDD6F4"
        self.fg_dim = "#A6ADC8"
        self.accent_color = "#89B4FA"
        self.accent_green = "#A6E3A1"
        self.accent_orange = "#FAB387"
        self.btn_bg = "#313244"
        
        self.configure(bg=self.bg_main)
        self.config = self._load_config()
        
        # Các biến giao diện
        self.var_engine_mode = tk.StringVar(value=self.config.get("engine_mode", "colab"))
        self.var_colab_url = tk.StringVar(value=self.config.get("colab_url", ""))
        self.var_colab_status = tk.StringVar(value="Chưa kiểm tra kết nối")
        
        self.var_drafts_dir = tk.StringVar(value=self.config.get("drafts_dir", ""))
        self.var_language = tk.StringVar(value=self.config.get("language", "Tiếng Việt (vi)"))
        self.var_model = tk.StringVar(value=self.config.get("model", "large-v3"))
        self.var_dry_run = tk.BooleanVar(value=self.config.get("dry_run", False))
        self.var_max_words = tk.IntVar(value=self.config.get("max_words", 13))
        
        self.lang_map = {
            "Tiếng Việt (vi)": "vi",
            "Tự động nhận diện": None,
            "Tiếng Anh (en)": "en",
            "Tiếng Trung (zh)": "zh",
            "Tiếng Hàn (ko)": "ko",
            "Tiếng Nhật (ja)": "ja"
        }
        
        self._init_styles()
        self._create_widgets()
        
        self.var_drafts_dir.trace_add("write", lambda *args: self._on_drafts_dir_change())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        if self.var_drafts_dir.get():
            self.after(500, self._refresh_draft_list)
            
        # Tự động ping Colab nếu đã có link từ trước
        if self.var_colab_url.get():
            self.after(1000, self._test_colab_connection)

    def _init_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        self.style.configure("Treeview", 
                             background=self.bg_frame, 
                             foreground=self.fg_main, 
                             fieldbackground=self.bg_frame,
                             rowheight=26,
                             font=("Segoe UI", 10))
        self.style.map("Treeview", background=[("selected", self.accent_color)], foreground=[("selected", "#1E1E2E")])
        self.style.configure("Treeview.Heading", 
                             background=self.btn_bg, 
                             foreground=self.fg_main, 
                             font=("Segoe UI", 10, "bold"),
                             borderwidth=1)
        self.style.configure("TLabelframe", background=self.bg_main, foreground=self.accent_color, font=("Segoe UI", 11, "bold"))
        self.style.configure("TLabelframe.Label", background=self.bg_main, foreground=self.accent_color)

    def _create_widgets(self):
        # 1. Header Tiêu đề ứng dụng
        header_frame = tk.Frame(self, bg=self.bg_main, pady=8)
        header_frame.pack(fill=tk.X)
        
        title_label = tk.Label(header_frame, text="CAPCUT AUDIO TO TEXT TOOL", font=("Segoe UI", 17, "bold"), 
                               bg=self.bg_main, fg=self.accent_color)
        title_label.pack(side=tk.LEFT, padx=20)
        
        subtitle = tk.Label(header_frame, text="Google Colab GPU Tesla T4 (Whisper Large-v3) & Local Offline", 
                            font=("Segoe UI", 10, "italic"), bg=self.bg_main, fg=self.fg_dim)
        subtitle.pack(side=tk.LEFT, padx=10)
        
        # Paned Window chia 2 nửa: Cấu hình phía trên và Output Log phía dưới
        main_paned = tk.PanedWindow(self, orient=tk.VERTICAL, bg=self.bg_main, bd=0, sashwidth=4, sashrelief=tk.FLAT)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        top_frame = tk.Frame(main_paned, bg=self.bg_main)
        main_paned.add(top_frame, minsize=440)
        
        top_left_frame = tk.Frame(top_frame, bg=self.bg_main)
        top_left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        top_right_frame = tk.Frame(top_frame, bg=self.bg_main)
        top_right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # --- CỘT TRÁI ---
        # 1. KHỐI ĐỘNG CƠ XỬ LÝ (STT ENGINE)
        lf_engine = tk.LabelFrame(top_left_frame, text="1. Động cơ nhận diện (STT Engine)", bg=self.bg_frame, fg=self.accent_color,
                                  font=("Segoe UI", 10, "bold"), padx=10, pady=8, bd=1, relief=tk.SOLID)
        lf_engine.pack(fill=tk.X, pady=(0, 8))
        
        # Radio chọn Colab vs Local
        r_box = tk.Frame(lf_engine, bg=self.bg_frame)
        r_box.pack(fill=tk.X, pady=(0, 6))
        
        r_colab = tk.Radiobutton(r_box, text="🚀 Google Colab GPU (Tesla T4 16GB - Whisper Large-v3)", 
                                 variable=self.var_engine_mode, value="colab", bg=self.bg_frame, fg=self.accent_green,
                                 activebackground=self.bg_frame, activeforeground=self.accent_green,
                                 selectcolor=self.bg_main, font=("Segoe UI", 10, "bold"),
                                 command=self._on_engine_change)
        r_colab.pack(side=tk.LEFT, padx=(0, 15))
        
        r_local = tk.Radiobutton(r_box, text="💻 Local Offline", 
                                 variable=self.var_engine_mode, value="local", bg=self.bg_frame, fg=self.fg_main,
                                 activebackground=self.bg_frame, activeforeground=self.fg_main,
                                 selectcolor=self.bg_main, font=("Segoe UI", 10),
                                 command=self._on_engine_change)
        r_local.pack(side=tk.LEFT)
        
        # Khung cấu hình link Colab
        self.frame_colab_settings = tk.Frame(lf_engine, bg=self.bg_frame)
        self.frame_colab_settings.pack(fill=tk.X, pady=4)
        
        tk.Label(self.frame_colab_settings, text="Link Cloudflare Colab:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=tk.W, pady=2)
        
        self.entry_colab = tk.Entry(self.frame_colab_settings, textvariable=self.var_colab_url, bg=self.bg_main, fg=self.fg_main,
                                    insertbackground=self.fg_main, bd=1, relief=tk.SOLID, font=("Consolas", 10))
        self.entry_colab.grid(row=0, column=1, sticky=tk.EW, padx=6, pady=2)
        
        self.btn_check_colab = tk.Button(self.frame_colab_settings, text="Kiểm tra kết nối", bg=self.btn_bg, fg=self.accent_color,
                                         activebackground=self.accent_color, activeforeground=self.bg_main, bd=0, padx=8, pady=2,
                                         font=("Segoe UI", 9, "bold"), cursor="hand2", command=self._test_colab_connection)
        self.btn_check_colab.grid(row=0, column=2, pady=2)
        
        self.lbl_colab_status = tk.Label(self.frame_colab_settings, textvariable=self.var_colab_status, bg=self.bg_frame, fg=self.fg_dim, font=("Segoe UI", 9))
        self.lbl_colab_status.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=6, pady=(2, 0))
        self.frame_colab_settings.columnconfigure(1, weight=1)
        
        # Khung cấu hình Local Model
        self.frame_local_settings = tk.Frame(lf_engine, bg=self.bg_frame)
        tk.Label(self.frame_local_settings, text="Model Local:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 6))
        self.cb_local_model = ttk.Combobox(self.frame_local_settings, textvariable=self.var_model,
                                           values=["tiny", "base", "small", "medium", "large", "large-v3", "large-v3-turbo"],
                                           state="readonly", width=14, font=("Segoe UI", 9))
        self.cb_local_model.pack(side=tk.LEFT, padx=(0, 8))
        btn_save_model = tk.Button(self.frame_local_settings, text="Lưu mặc định", bg=self.btn_bg, fg=self.fg_main, bd=0, padx=6, font=("Segoe UI", 8), command=self._save_model_default)
        btn_save_model.pack(side=tk.LEFT)
        
        # 2. KHỐI ĐƯỜNG DẪN HỆ THỐNG
        lf_paths = tk.LabelFrame(top_left_frame, text="2. Thư mục dự án CapCut", bg=self.bg_frame, fg=self.accent_color,
                                  font=("Segoe UI", 10, "bold"), padx=10, pady=8, bd=1, relief=tk.SOLID)
        lf_paths.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(lf_paths, text="Đường dẫn Drafts:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 9)).grid(row=0, column=0, sticky=tk.W, pady=3)
        entry_drafts = tk.Entry(lf_paths, textvariable=self.var_drafts_dir, bg=self.bg_main, fg=self.fg_main, insertbackground=self.fg_main, bd=1, relief=tk.SOLID, font=("Segoe UI", 9))
        entry_drafts.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=3)
        btn_browse_drafts = tk.Button(lf_paths, text="Browse...", bg=self.btn_bg, fg=self.fg_main, activebackground=self.accent_color, activeforeground=self.bg_main, bd=0, padx=8, font=("Segoe UI", 9), command=self._browse_drafts_dir)
        btn_browse_drafts.grid(row=0, column=2, pady=3)
        lf_paths.columnconfigure(1, weight=1)
        
        # 3. KHỐI TÙY CHỌN CHUYỂN ĐỔI
        lf_options = tk.LabelFrame(top_left_frame, text="3. Tùy chọn chuyển đổi phụ đề", bg=self.bg_frame, fg=self.accent_color,
                                    font=("Segoe UI", 10, "bold"), padx=10, pady=8, bd=1, relief=tk.SOLID)
        lf_options.pack(fill=tk.BOTH, expand=True)
        
        # Ngôn ngữ
        tk.Label(lf_options, text="Ngôn ngữ voice:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 9)).grid(row=0, column=0, sticky=tk.W, pady=5)
        cb_lang = ttk.Combobox(lf_options, textvariable=self.var_language, values=list(self.lang_map.keys()), state="readonly", font=("Segoe UI", 9))
        cb_lang.grid(row=0, column=1, sticky=tk.W, padx=8, pady=5)
        
        # Giới hạn từ
        tk.Label(lf_options, text="Giới hạn từ/đoạn:", bg=self.bg_frame, fg=self.fg_main, font=("Segoe UI", 9)).grid(row=1, column=0, sticky=tk.W, pady=5)
        sb_words = tk.Spinbox(lf_options, from_=1, to=100, textvariable=self.var_max_words, width=8, bg=self.bg_main, fg=self.fg_main, insertbackground=self.fg_main, bd=1, relief=tk.SOLID, font=("Segoe UI", 9))
        sb_words.grid(row=1, column=1, sticky=tk.W, padx=8, pady=5)
        
        # Dry Run
        chk_dry = tk.Checkbutton(lf_options, text="Chạy thử nghiệm (Dry-Run - Không lưu vào file)", variable=self.var_dry_run, 
                                 bg=self.bg_frame, fg=self.fg_main, activebackground=self.bg_frame, activeforeground=self.fg_main,
                                 selectcolor=self.bg_main, font=("Segoe UI", 9))
        chk_dry.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=6)
        
        # Nút chuyển đổi 1: Gom nhóm
        self.btn_convert = tk.Button(lf_options, text="⚡ CHUYỂN ĐỔI VOICE → TEXT (NHÓM SUB)", bg=self.accent_color, fg="#1E1E2E",
                                     activebackground="#b4befe", activeforeground="#1E1E2E", font=("Segoe UI", 10, "bold"),
                                     bd=0, height=2, cursor="hand2", command=lambda: self._start_conversion_thread(group_subtitles=True))
        self.btn_convert.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(8, 4))
        
        # Nút chuyển đổi 2: Không gom nhóm
        self.btn_convert_nogroup = tk.Button(lf_options, text="CHUYỂN ĐỔI (KHÔNG ÁP DỤNG TẤT CẢ)", bg=self.accent_orange, fg="#1E1E2E",
                                             activebackground="#f9e2af", activeforeground="#1E1E2E", font=("Segoe UI", 9, "bold"),
                                             bd=0, height=1, cursor="hand2", command=lambda: self._start_conversion_thread(group_subtitles=False))
        self.btn_convert_nogroup.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=(2, 4))
        
        lf_options.columnconfigure(1, weight=1)
        
        # --- CỘT PHẢI: DANH SÁCH DỰ ÁN ---
        lf_drafts = tk.LabelFrame(top_right_frame, text="Danh sách dự án (Drafts)", bg=self.bg_frame, fg=self.accent_color,
                                   font=("Segoe UI", 10, "bold"), padx=10, pady=8, bd=1, relief=tk.SOLID)
        lf_drafts.pack(fill=tk.BOTH, expand=True)
        
        header_drafts = tk.Frame(lf_drafts, bg=self.bg_frame)
        header_drafts.pack(fill=tk.X, pady=(0, 6))
        
        lbl_drafts_info = tk.Label(header_drafts, text="Dự án khả dụng:", bg=self.bg_frame, fg=self.fg_dim, font=("Segoe UI", 9, "italic"))
        lbl_drafts_info.pack(side=tk.LEFT, anchor=tk.CENTER)
        
        btn_refresh = tk.Button(header_drafts, text="Làm mới (Refresh)", bg=self.btn_bg, fg=self.fg_main,
                                activebackground=self.accent_color, activeforeground=self.bg_main,
                                bd=0, padx=10, pady=3, font=("Segoe UI", 9, "bold"), command=self._refresh_draft_list)
        btn_refresh.pack(side=tk.RIGHT, anchor=tk.CENTER)
        
        tree_container = tk.Frame(lf_drafts, bg=self.bg_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        cols = ("name", "status")
        self.tree_drafts = ttk.Treeview(tree_container, columns=cols, show="headings", selectmode="browse")
        self.tree_drafts.heading("name", text="Tên dự án (Draft Name)")
        self.tree_drafts.heading("status", text="Trạng thái (Status)")
        self.tree_drafts.column("name", width=250, anchor=tk.W)
        self.tree_drafts.column("status", width=120, anchor=tk.CENTER)
        
        tree_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree_drafts.yview)
        self.tree_drafts.configure(yscrollcommand=tree_scroll.set)
        self.tree_drafts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # --- KHỐI DƯỚI CÙNG: OUTPUT LOG ---
        log_frame = tk.LabelFrame(main_paned, text="Output Log", bg=self.bg_frame, fg=self.accent_color,
                                  font=("Segoe UI", 10, "bold"), padx=10, pady=8, bd=1, relief=tk.SOLID)
        main_paned.add(log_frame, minsize=220)
        
        self.txt_log = tk.Text(log_frame, bg=self.bg_main, fg=self.fg_main, insertbackground=self.fg_main,
                               wrap=tk.WORD, font=("Consolas", 10), state=tk.DISABLED, bd=0)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scrollbar.set)
        
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log("Ứng dụng CapCut Audio to Text Tool đã sẵn sàng!")
        self.log("Khuyến nghị: Sử dụng chế độ 'Google Colab GPU Tesla T4' để tận dụng Whisper Large-v3 siêu tốc.")
        
        self._on_engine_change()

    # --- CÁC HÀM XỬ LÝ SỰ KIỆN GIAO DIỆN ---
    def log(self, message):
        """Ghi thông tin kèm timestamp vào Output Log."""
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
        self.txt_log.configure(state=tk.NORMAL)
        self.txt_log.insert(tk.END, f"{timestamp} {message}\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state=tk.DISABLED)

    def _on_engine_change(self):
        mode = self.var_engine_mode.get()
        if mode == "colab":
            self.frame_local_settings.pack_forget()
            self.frame_colab_settings.pack(fill=tk.X, pady=4)
        else:
            self.frame_colab_settings.pack_forget()
            self.frame_local_settings.pack(fill=tk.X, pady=4)
        self._save_config()

    def _test_colab_connection(self):
        url = self.var_colab_url.get().strip()
        if not url:
            self.var_colab_status.set("Chưa nhập link Colab!")
            self.lbl_colab_status.configure(fg="#F38BA8")
            return
            
        self.var_colab_status.set("Đang kiểm tra kết nối GPU Tesla T4...")
        self.lbl_colab_status.configure(fg=self.accent_color)
        self._save_config()
        
        def run_check():
            ok, msg = check_colab_health(url)
            if ok:
                self.var_colab_status.set(f"✅ {msg}")
                self.lbl_colab_status.configure(fg=self.accent_green)
                self.log(f"[KẾT NỐI COLAB THÀNH CÔNG] {msg}")
            else:
                self.var_colab_status.set(f"❌ {msg}")
                self.lbl_colab_status.configure(fg="#F38BA8")
                self.log(f"[LỖI KẾT NỐI COLAB] {msg}")
                
        threading.Thread(target=run_check, daemon=True).start()

    def _load_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        default_config = {
            "engine_mode": "colab",
            "colab_url": "",
            "drafts_dir": get_default_drafts_dir(),
            "language": "Tiếng Việt (vi)",
            "model": "large-v3",
            "dry_run": False,
            "max_words": 13
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    default_config.update(saved)
            except Exception:
                pass
        if not default_config.get("drafts_dir"):
            default_config["drafts_dir"] = get_default_drafts_dir()
        return default_config

    def _save_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        try:
            config_data = {
                "engine_mode": self.var_engine_mode.get(),
                "colab_url": self.var_colab_url.get().strip(),
                "drafts_dir": self.var_drafts_dir.get(),
                "language": self.var_language.get(),
                "model": self.var_model.get(),
                "dry_run": self.var_dry_run.get(),
                "max_words": int(self.var_max_words.get())
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def _on_close(self):
        self._save_config()
        self.destroy()

    def _save_model_default(self):
        self._save_config()
        self.log(f"Đã lưu model local mặc định: '{self.var_model.get()}'")
        messagebox.showinfo("Thành công", f"Đã lưu model '{self.var_model.get()}' làm mặc định cho Local!")

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
        for item in self.tree_drafts.get_children():
            self.tree_drafts.delete(item)
            
        drafts_root = self.var_drafts_dir.get()
        if not drafts_root:
            return
            
        self.log("Đang quét danh sách dự án CapCut...")
        drafts = find_drafts(drafts_root)
        for d in drafts:
            self.tree_drafts.insert("", tk.END, values=(d["name"], d["status"]), tags=(d["path"],))
        self.log(f"Đã quét xong. Tìm thấy {len(drafts)} dự án.")

    def _is_capcut_running(self):
        import subprocess
        try:
            output = subprocess.check_output('tasklist', shell=True).decode('utf-8', errors='ignore').lower()
            return "capcut" in output
        except Exception:
            return False

    def _start_conversion_thread(self, group_subtitles=True):
        selected_project_path = ""
        selected_item = self.tree_drafts.selection()
        if selected_item:
            tags = self.tree_drafts.item(selected_item[0], "tags")
            if tags:
                selected_project_path = tags[0]
                
        if not selected_project_path:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một dự án trong danh sách trước khi chuyển đổi!")
            return
            
        engine = self.var_engine_mode.get()
        if engine == "colab":
            colab_url = self.var_colab_url.get().strip()
            if not colab_url or not colab_url.startswith("http"):
                messagebox.showerror("Thiếu link Colab", "Bạn đang chọn chế độ 'Google Colab GPU' nhưng chưa nhập link Cloudflare!\nHãy chạy file Colab và dán link (https://xxxx.trycloudflare.com) vào ô tương ứng.")
                return

        if self._is_capcut_running():
            proceed = messagebox.askokcancel(
                "Lưu ý quan trọng",
                "Phần mềm CapCut hiện tại đang mở trên máy.\n\n"
                "QUAN TRỌNG: Bạn CẦN thoát dự án này ra ngoài màn hình Trang chủ (Homepage) của CapCut hoặc đóng CapCut lại.\n"
                "Nếu vẫn mở màn hình edit dự án này, CapCut sẽ tự động ghi đè và làm MẤT phụ đề mới chèn.\n\n"
                "Bạn đã quay ra Trang chủ và muốn tiếp tục?"
            )
            if not proceed:
                return
                
        self.btn_convert.configure(state=tk.DISABLED, text="ĐANG XỬ LÝ...")
        self.btn_convert_nogroup.configure(state=tk.DISABLED, text="ĐANG XỬ LÝ...")
        
        t = threading.Thread(target=self._process_conversion, args=(selected_project_path, group_subtitles))
        t.daemon = True
        t.start()

    def _process_conversion(self, project_path, group_subtitles=True):
        engine_mode = self.var_engine_mode.get()
        colab_url = self.var_colab_url.get().strip()
        language_display = self.var_language.get()
        language_code = self.lang_map.get(language_display)
        model_size = self.var_model.get()
        dry_run = self.var_dry_run.get()
        max_words = self.var_max_words.get()
        
        self._save_config()
        
        self.log("=" * 60)
        self.log(f"KHỞI ĐỘNG CHUYỂN ĐỔI DỰ ÁN CAPCUT:")
        self.log(f"  Dự án: {os.path.basename(project_path)}")
        if engine_mode == "colab":
            self.log(f"  Động cơ: Google Colab GPU (Tesla T4 16GB - Whisper Large-v3)")
            self.log(f"  Colab URL: {colab_url}")
        else:
            self.log(f"  Động cơ: Local Máy tính Offline (Model: {model_size})")
        self.log(f"  Giới hạn từ: {max_words} từ / đoạn | Chế độ: {'Thử nghiệm (Dry-Run)' if dry_run else 'Ghi trực tiếp'}")
        
        try:
            candidates = find_audio_candidates(project_path)
            if not candidates:
                raise FileNotFoundError("Không tìm thấy bất kỳ file audio/video nào trên timeline của dự án này!")
            
            segments = None
            last_error = None
            successful_audio_path = None
            successful_offset_us = 0
            
            for item in candidates:
                audio_path = item["path"]
                offset_us = item["offset_us"]
                self.log(f"Thử nghiệm nhận diện file media: {os.path.basename(audio_path)}")
                try:
                    if engine_mode == "colab":
                        candidate_segments = transcribe_audio_colab(colab_url, audio_path, language_code, self.log)
                    else:
                        candidate_segments = transcribe_audio_local(audio_path, language_code, model_size, self.log)
                        
                    if candidate_segments or item == candidates[-1]:
                        segments = candidate_segments
                        successful_audio_path = audio_path
                        successful_offset_us = offset_us
                        if candidate_segments:
                            break
                        else:
                            self.log(f"[THÔNG TIN] File {os.path.basename(audio_path)} thành công nhưng không chứa giọng nói (0 đoạn).")
                    else:
                        self.log(f"[THÔNG TIN] File {os.path.basename(audio_path)} không phát hiện giọng nói, đang thử file tiếp theo...")
                except Exception as ex:
                    last_error = ex
                    self.log(f"[CẢNH BÁO] Bỏ qua file do lỗi giải mã: {os.path.basename(audio_path)}")
            
            if segments is None:
                raise RuntimeError(f"Tất cả các file audio/video đều không thể xử lý. Lỗi cuối: {last_error}")
            
            # Chia nhỏ các câu quá dài (tối đa max_words từ) và bảo vệ từ ghép tiếng Việt
            segments = split_segments_by_words(segments, max_words=max_words)
            
            # Chèn dữ liệu vào draft_content.json
            inserted = insert_text_into_draft(project_path, segments, dry_run, self.log, timeline_offset_us=successful_offset_us, group_subtitles=group_subtitles)
            
            mode_text = " (Chạy thử nghiệm)" if dry_run else ""
            engine_text = "Colab GPU Tesla T4 (Whisper Large-v3)" if engine_mode == "colab" else f"Local ({model_size})"
            messagebox.showinfo("Thành công", f"Đã hoàn thành chuyển đổi{mode_text}!\nĐộng cơ: {engine_text}\nĐã xử lý {inserted} đoạn phụ đề từ file: {os.path.basename(successful_audio_path)}.")
            
        except Exception as e:
            self.log(f"[THẤT BẠI] Quá trình xử lý bị dừng do lỗi: {e}")
            messagebox.showerror("Lỗi xử lý", f"Đã xảy ra lỗi trong quá trình chuyển đổi:\n{e}")
            
        finally:
            self.btn_convert.configure(state=tk.NORMAL, text="⚡ CHUYỂN ĐỔI VOICE → TEXT (NHÓM SUB)")
            self.btn_convert_nogroup.configure(state=tk.NORMAL, text="CHUYỂN ĐỔI (KHÔNG ÁP DỤNG TẤT CẢ)")
            self.log("=" * 60)

if __name__ == "__main__":
    app = CapCutAudioToTextApp()
    app.mainloop()
