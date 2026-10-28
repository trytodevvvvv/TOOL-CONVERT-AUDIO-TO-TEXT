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
import webbrowser
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Kích hoạt Per-Monitor High-DPI Awareness cho Windows
# Giúp phông chữ, bảng biểu và viền bo hiển thị sắc nét pixel-perfect, loại bỏ hoàn toàn mờ nhòe/giật pixel
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ==============================================================================
# PHẦN 1: THIẾT LẬP MÔI TRƯỜNG & HỆ THỐNG
# ==============================================================================

def setup_ffmpeg_path():
    """
    Tự động dò tìm và nạp đường dẫn FFmpeg vào PATH hệ thống
    để trích xuất và nén audio siêu tốc sang 16kHz mono FLAC.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        current_dir,
        os.path.join(current_dir, "CapCut_STT_Tool"),
        os.path.join(current_dir, "ffmpeg"),
        os.path.join(current_dir, "ffmpeg", "bin"),
        os.path.dirname(current_dir)
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.exists(os.path.join(c, "ffmpeg.exe")):
            if c not in os.environ.get("PATH", ""):
                os.environ["PATH"] = c + os.pathsep + os.environ.get("PATH", "")
            return
            
    if shutil.which("ffmpeg"):
        return
            
    try:
        import importlib
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        ffmpeg_exe = getattr(imageio_ffmpeg, "get_ffmpeg_exe", lambda: "")()
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)
            target_ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            if not os.path.exists(target_ffmpeg):
                try: shutil.copyfile(ffmpeg_exe, target_ffmpeg)
                except Exception: pass
            local_ffmpeg = os.path.join(current_dir, "ffmpeg.exe")
            if not os.path.exists(local_ffmpeg):
                try: shutil.copyfile(ffmpeg_exe, local_ffmpeg)
                except Exception: pass
            os.environ["PATH"] = current_dir + os.pathsep + ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

setup_ffmpeg_path()

def get_default_drafts_dir():
    """Tự động phát hiện thư mục lưu trữ dự án CapCut PC."""
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

def get_capcut_font_path():
    """Tự động tìm font chữ mặc định của CapCut."""
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

# ==============================================================================
# PHẦN 2: COLAB GPU CLIENT & AUDIO PROCESSING
# ==============================================================================

def get_colab_run_code():
    """
    Sinh toàn bộ mã nguồn Colab hoàn chỉnh để người dùng copy 1-click
    và dán vào 1 ô duy nhất trên Google Colab chạy ngay.
    """
    return """# ==============================================================================
# 🎙️ WHISPER LARGE-V3 GPU SERVER - GOOGLE COLAB (TESLA T4 16GB)
# ==============================================================================
# BƯỚC 1: Cài đặt thư viện Faster-Whisper, FastAPI & Cloudflared
# ==============================================================================
!pip install -q faster-whisper "av<18" nvidia-cublas-cu12 nvidia-cudnn-cu12 fastapi uvicorn pydantic nest-asyncio soundfile
!wget -q -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
!dpkg -i cloudflared-linux-amd64.deb > /dev/null 2>&1
print("✅ [1/2] Đã cài đặt hoàn tất các gói thư viện!")

# ==============================================================================
# BƯỚC 2: Khởi chạy Server Whisper Large-v3 (Batched 13.5GB VRAM) & Cloudflare
# ==============================================================================
import os, io, time, base64, tempfile, threading, subprocess, re, uuid, gc, glob, site, ctypes
from typing import Optional

# 1. Cấu hình và nạp thư viện CUDA 12 (libcublas, libcudnn) cho CTranslate2
for sp in site.getsitepackages():
    cublas_lib = os.path.join(sp, "nvidia", "cublas", "lib")
    cudnn_lib = os.path.join(sp, "nvidia", "cudnn", "lib")
    if os.path.exists(cublas_lib):
        try:
            with open("/etc/ld.so.conf.d/nvidia-cu12.conf", "w") as f:
                f.write(cublas_lib + chr(10) + cudnn_lib + chr(10))
            subprocess.run(["ldconfig"], check=False)
        except Exception:
            pass
        os.environ["LD_LIBRARY_PATH"] = f"{cublas_lib}:{cudnn_lib}:" + os.environ.get("LD_LIBRARY_PATH", "")
        for lib_file in sorted(glob.glob(os.path.join(cublas_lib, "*.so*")) + glob.glob(os.path.join(cudnn_lib, "*.so*"))):
            try:
                ctypes.CDLL(lib_file, mode=ctypes.RTLD_GLOBAL)
            except Exception:
                pass
        break

# 2. Vá lỗi tương thích giữa PyAV và faster-whisper (loại bỏ metadata_errors trên PyAV 18+)
try:
    import av
    _orig_av_open = av.open
    def _safe_av_open(*args, metadata_errors=None, **kwargs):
        return _orig_av_open(*args, **kwargs)
    av.open = _safe_av_open
except Exception:
    pass

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import torch, nest_asyncio, uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from faster_whisper import WhisperModel, BatchedInferencePipeline

if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"
BATCH_SIZE = 24  # Batching 24 block âm thanh song song đẩy VRAM lên 13.0 - 13.5 GB
BEAM_SIZE = 5    # SOTA accuracy

print(f"--> Đang nạp model Whisper Large-v3 vào GPU ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})...")
base_model = WhisperModel("large-v3", device=DEVICE, compute_type=COMPUTE_TYPE, cpu_threads=4, num_workers=2)

try:
    batched_pipeline = BatchedInferencePipeline(model=base_model)
    print("--> Kích hoạt BatchedInferencePipeline thành công!")
except Exception as e:
    batched_pipeline = None

# Thực hiện Warm-up và kiểm tra CUDA inference thực tế (ép CTranslate2 load cuBLAS)
if torch.cuda.is_available():
    try:
        import numpy as np
        print("--> Đang kiểm tra và Warm-up GPU Tesla T4...")
        dummy_audio = np.zeros(16000 * 2, dtype=np.float32)
        gen, _ = base_model.transcribe(dummy_audio, beam_size=1)
        _ = list(gen) # CƯỠNG BỨC chạy phép tính ma trận cuBLAS
        torch.cuda.empty_cache()
        print("--> Warm-up hoàn tất: GPU Tesla T4 & cuBLAS đã sẵn sàng 100%!")
    except Exception as e:
        print(f"--> Cảnh báo Warm-up GPU: {e}")

app = FastAPI(title="Whisper Large-v3 Colab Server")

class TranscribeRequest(BaseModel):
    audio_base64: str
    audio_ext: Optional[str] = "flac"
    language: Optional[str] = "vi"
    batch_size: Optional[int] = 24
    beam_size: Optional[int] = 5
    vad_filter: Optional[bool] = True

TASKS = {}
TASKS_LOCK = threading.Lock()

LANGUAGE_PROMPTS = {
    "vi": "Sau đây là bài thuyết minh chất lượng cao, chuẩn tiếng Việt, có đầy đủ dấu câu, ngữ pháp chính xác, viết hoa đúng chuẩn.",
    "en": "The following is a clear, high-quality narration with correct punctuation, capitalization, and grammar.",
    "ko": "다음은 명확하고 고품질의 내레이션으로, 올바른 맞춤법, 띄어쓰기, 문장 부호(., ?) 및 표준어를 사용합니다.",
    "ja": "以下は、句読点（、。）を適切に配置し、自然な日本語の文法と正確な漢字表記を用いた高品質なナレーションです。",
    "es": "La siguiente es una narración clara y de alta calidad, con puntuación correcta (¿?, ¡!), acentuación adecuada y ortografía precisa.",
    "pt": "A seguir está uma narração clara e de alta qualidade, com pontuação correta, acentuação adequada e excelente gramática em português.",
    "pt-BR": "A seguir está uma narração clara e de alta qualidade, com pontuação correta, acentuação adequada e excelente gramática em português do Brasil.",
    "zh": "以下是一段高质量的解说，标点符号（，。）规范，语法标准，用词准确。"
}

def _execute_transcribe(req: TranscribeRequest):
    raw_bytes = base64.b64decode(req.audio_base64)
    ext = req.audio_ext or "flac"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            f.write(raw_bytes)
            tmp_path = f.name

        raw_lang = (req.language or "").strip()
        if not raw_lang or raw_lang.lower() in ("auto", "none"):
            target_lang = None
            initial_prompt = None
        elif raw_lang == "pt-BR":
            target_lang = "pt"
            initial_prompt = LANGUAGE_PROMPTS.get("pt-BR")
        else:
            target_lang = raw_lang
            initial_prompt = LANGUAGE_PROMPTS.get(target_lang, None)

        batch_size = req.batch_size or BATCH_SIZE
        beam_size = req.beam_size or BEAM_SIZE
        vad = True if req.vad_filter is None else req.vad_filter

        vad_params = dict(
            threshold=0.35,
            min_speech_duration_ms=250,
            min_silence_duration_ms=1000,
            speech_pad_ms=500
        )

        transcribe_kwargs = dict(
            beam_size=beam_size,
            language=target_lang,
            vad_filter=vad,
            vad_parameters=vad_params,
            word_timestamps=True,
            initial_prompt=initial_prompt,
            repetition_penalty=1.15,
            hallucination_silence_threshold=2.0
        )

        start_t = time.time()
        if batched_pipeline is not None and DEVICE == "cuda":
            segments_gen, info = batched_pipeline.transcribe(
                tmp_path,
                batch_size=batch_size,
                **transcribe_kwargs
            )
        else:
            segments_gen, info = base_model.transcribe(
                tmp_path,
                **transcribe_kwargs
            )

        parsed_segments = []
        for s in segments_gen:
            words_data = []
            if hasattr(s, "words") and s.words:
                for w in s.words:
                    words_data.append({
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                        "word": w.word.strip()
                    })
            parsed_segments.append({
                "start": round(float(s.start), 3),
                "end": round(float(s.end), 3),
                "text": s.text.strip(),
                "words": words_data
            })

        return {
            "success": True,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 4) if hasattr(info, "language_probability") else 1.0,
            "audio_duration_sec": round(float(info.duration), 2) if hasattr(info, "duration") else 0.0,
            "processing_time_sec": round(time.time() - start_t, 2),
            "total_segments": len(parsed_segments),
            "segments": parsed_segments
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except Exception: pass
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def _async_worker(task_id: str, req: TranscribeRequest):
    try:
        res = _execute_transcribe(req)
        with TASKS_LOCK:
            TASKS[task_id] = {"status": "completed", "result": res}
    except Exception as e:
        with TASKS_LOCK:
            TASKS[task_id] = {"status": "failed", "error": str(e)}
    finally:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

@app.get("/")
@app.get("/health")
def health():
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    free_mem, total_mem = torch.cuda.mem_get_info(0) if torch.cuda.is_available() else (0, 0)
    used_mem = total_mem - free_mem
    return {
        "status": "ready",
        "device": DEVICE,
        "gpu_name": gpu_name,
        "vram_used_gb": round(used_mem / (1024**3), 2),
        "vram_free_gb": round(free_mem / (1024**3), 2),
        "vram_total_gb": round(total_mem / (1024**3), 2)
    }

@app.post("/transcribe")
def transcribe_sync(req: TranscribeRequest):
    return _execute_transcribe(req)

@app.post("/task_submit")
def task_submit(req: TranscribeRequest):
    task_id = str(uuid.uuid4())
    with TASKS_LOCK:
        TASKS[task_id] = {"status": "processing"}
    th = threading.Thread(target=_async_worker, args=(task_id, req), daemon=True)
    th.start()
    return {"task_id": task_id}

@app.get("/task_status/{task_id}")
def task_status(task_id: str):
    with TASKS_LOCK:
        if task_id not in TASKS:
            return {"status": "not_found"}
        return TASKS[task_id]

@app.post("/task_clear/{task_id}")
def task_clear(task_id: str):
    with TASKS_LOCK:
        if task_id in TASKS:
            del TASKS[task_id]
    return {"status": "cleared"}

# Khởi động Uvicorn ngầm và Cloudflare Tunnel
nest_asyncio.apply()

def run_uvicorn():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

server_th = threading.Thread(target=run_uvicorn, daemon=True)
server_th.start()
time.sleep(2)

if os.path.exists("cloudflare.log"):
    try: os.remove("cloudflare.log")
    except Exception: pass

tunnel_proc = subprocess.Popen(
    ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8000", "--logfile", "cloudflare.log"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

public_url = None
for _ in range(35):
    time.sleep(1)
    if os.path.exists("cloudflare.log"):
        with open("cloudflare.log", "r", encoding="utf-8", errors="ignore") as f:
            matches = re.findall(r"https://[a-zA-Z0-9-]+\\.trycloudflare\\.com", f.read())
            if matches:
                public_url = matches[0]
                break

if public_url:
    print("=" * 70)
    print("🚀 KẾT NỐI GPU COLAB THÀNH CÔNG (TESLA T4 16GB - WHISPER LARGE-V3)!")
    print(f"👉 DÁN LINK NÀY VÀO TOOL DESKTOP: {public_url}")
    print("=" * 70)
    print("⏳ Server đang chạy ngầm... Giữ tab Google Colab mở để duy trì GPU.")
    try: tunnel_proc.wait()
    except KeyboardInterrupt: print("Đã dừng server.")
else:
    print("❌ Lỗi: Không thể lấy được link Cloudflare. Vui lòng thử lại.")
"""

# ==============================================================================
# PHẦN 3: XỬ LÝ VĂN BẢN & XUẤT PHỤ ĐỀ CAPCUT / SRT
# ==============================================================================

import re
from collections import Counter

HALLUCINATION_PATTERNS = [
    # Tiếng Việt
    r"đăng\s*ký\s*kênh", r"ủng\s*hộ\s*kênh", r"subscribe.*kênh", r"ghiền\s*mì\s*gõ", r"la\s*la\s*school",
    r"cảm\s*ơn\s*các\s*bạn\s*đã\s*theo\s*dõi", r"hẹn\s*gặp\s*lại", r"hãy\s*like\s*và\s*share",
    # English
    r"thank\s*you\s*for\s*watching", r"thanks\s*for\s*watching", r"subscribe\s*to\s*(my|our|the)\s*channel",
    r"don'?t\s*forget\s*to\s*like", r"like\s*and\s*subscribe", r"subtitles\s*by", r"amara\.org",
    # Tiếng Hàn
    r"시청해\s*주셔서\s*감사합니다", r"구독과\s*좋아요", r"구독.*부탁드립니다", r"채널\s*구독",
    # Tiếng Nhật
    r"ご視聴ありがとうございました", r"チャンネル登録", r"高評価.*お願いします", r"最後までご視聴",
    # Tiếng Tây Ban Nha
    r"gracias\s*por\s*ver", r"suscr[íi]bete", r"dale\s*like", r"no\s*olvides\s*suscribirte",
    # Tiếng Bồ Đào Nha
    r"obrigado\s*por\s*assistir", r"inscreva-se", r"deixe\s*seu\s*like", r"compartilhe\s*este\s*v[íi]deo"
]
COMPILED_HALLUCINATIONS = [re.compile(p, re.IGNORECASE) for p in HALLUCINATION_PATTERNS]

def is_hallucination_or_repetitive(text, duration=None):
    clean = text.strip()
    if not clean:
        return True
    
    # 1. Kiểm tra danh sách đen cụm từ YouTube outro ma
    for p in COMPILED_HALLUCINATIONS:
        if p.search(clean):
            return True
            
    # 2. Kiểm tra vòng lặp token bất thường (ví dụ: A: A: A: hoặc nguồn nguồn nguồn)
    words = [w.strip(".,!?:;\"'()[]{}") for w in clean.split() if w.strip(".,!?:;\"'()[]{}")]
    if len(words) >= 4:
        streak = 1
        max_streak = 1
        for i in range(1, len(words)):
            if words[i].lower() == words[i-1].lower():
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 1
        if max_streak >= 3:
            return True
            
        c = Counter(w.lower() for w in words)
        top_word, count = c.most_common(1)[0]
        if count / len(words) >= 0.55:
            return True

    return False

def filter_hallucinations_and_loops(segments, language=None):
    """Lọc bỏ toàn bộ các câu ảo giác và vòng lặp từ vô tận."""
    clean_list = []
    for s in segments:
        txt = s.get("text", "").strip()
        dur = float(s.get("end", 0)) - float(s.get("start", 0))
        if dur <= 0.05 or not txt:
            continue
        if is_hallucination_or_repetitive(txt, duration=dur):
            continue
        clean_list.append(s)
    return clean_list

def reconcile_segment_overlaps(segments, min_duration=0.1, min_gap=0.03):
    """
    Đảm bảo 100% các đoạn phụ đề không bao giờ chồng lấn (overlap) mốc thời gian.
    Bảo đảm: segments[i]['start'] >= segments[i-1]['end'] + min_gap
    Loại bỏ hoàn toàn nguyên nhân CapCut tự sinh ra Track 8 / Layer 2.
    """
    if not segments:
        return []
        
    sorted_segs = sorted(segments, key=lambda x: float(x["start"]))
    clean_segs = []
    
    for seg in sorted_segs:
        start = float(seg["start"])
        end = float(seg["end"])
        text = seg.get("text", "").strip()
        
        if not text:
            continue
            
        if end <= start:
            end = start + min_duration
            
        if clean_segs:
            prev_end = clean_segs[-1]["end"]
            if start < prev_end:
                if prev_end > start:
                    clean_segs[-1]["end"] = max(clean_segs[-1]["start"] + min_duration, start - min_gap)
                if start < clean_segs[-1]["end"] + min_gap:
                    start = clean_segs[-1]["end"] + min_gap
                    end = max(start + min_duration, end)
                    
        clean_segs.append({
            "start": round(start, 3),
            "end": round(max(end, start + min_duration), 3),
            "text": text,
            "words": seg.get("words", [])
        })
        
    return clean_segs

def split_cjk_text(text, max_chars=20):
    """Tách đoạn chữ tượng hình tiếng Nhật (ja) / tiếng Trung (zh) không có dấu cách."""
    puncts = set("、。！？；：\n,.!?:;")
    chunks = []
    curr = []
    for ch in text:
        curr.append(ch)
        if ch in puncts or len(curr) >= max_chars:
            chunks.append("".join(curr).strip())
            curr = []
    if curr:
        chunks.append("".join(curr).strip())
    return [c for c in chunks if c]

def split_segment_with_words(seg, max_words=13):
    """Sử dụng trực tiếp Word Timestamps của Whisper để canh mốc từng mili-giây chuẩn xác."""
    words = seg.get("words", [])
    if not words or len(words) <= max_words:
        return [{"start": seg["start"], "end": seg["end"], "text": seg["text"]}]
        
    chunks = []
    curr_words = []
    
    for w in words:
        curr_words.append(w)
        word_str = w["word"].strip()
        ends_with_punct = bool(word_str and word_str[-1] in (',', '.', '?', '!', ';', ':', '—', '…', '¿', '¡', '，', '。', '？', '！', '、', '；', '：'))
        
        if len(curr_words) >= max_words or (ends_with_punct and len(curr_words) >= max(3, max_words - 4)):
            c_text = " ".join(cw["word"].strip() for cw in curr_words).strip()
            chunks.append({
                "start": curr_words[0]["start"],
                "end": curr_words[-1]["end"],
                "text": c_text
            })
            curr_words = []
            
    if curr_words:
        c_text = " ".join(cw["word"].strip() for cw in curr_words).strip()
        chunks.append({
            "start": curr_words[0]["start"],
            "end": curr_words[-1]["end"],
            "text": c_text
        })
        
    return chunks

def clean_word(word):
    import re
    return re.sub(r'[^\w\s]', '', word).lower().strip()

def wrap_text(text, max_chars=40):
    words = text.split()
    lines = []
    curr = []
    curr_len = 0
    for w in words:
        w_len = len(w)
        add = w_len + (1 if curr else 0)
        if curr_len + add <= max_chars:
            curr.append(w)
            curr_len += add
        else:
            if curr: lines.append(" ".join(curr))
            curr = [w]
            curr_len = w_len
    if curr: lines.append(" ".join(curr))
    return "\n".join(lines)

def split_segments_by_words(segments, max_words=13):
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
        base_size = total_words // num_chunks
        rem = total_words % num_chunks
        
        chunk_sizes = [base_size + (1 if i < rem else 0) for i in range(num_chunks)]
        split_indices = []
        curr = 0
        for sz in chunk_sizes[:-1]:
            curr += sz
            split_indices.append(curr)
            
        # Ưu tiên ngắt tại dấu câu
        for i in range(len(split_indices)):
            s_idx = split_indices[i]
            prev_s = split_indices[i - 1] if i > 0 else 0
            next_s = split_indices[i + 1] if i < len(split_indices) - 1 else total_words
            best_adj = None
            min_dist = 999
            
            for adj in range(max(prev_s + 1, s_idx - 3), min(next_s - 1, s_idx + 2) + 1):
                w = words[adj - 1]
                if w and w[-1] in (',', '.', '?', '!', ';', ':', '—', '…', '，', '。', '？', '！', '、', '；', '：'):
                    dist = abs(adj - s_idx)
                    if (adj - prev_s) <= max_words and (next_s - adj) <= max_words and dist < min_dist:
                        min_dist = dist
                        best_adj = adj
            if best_adj is not None:
                split_indices[i] = best_adj

        # Tránh cắt đôi từ ghép tiếng Việt
        for i in range(len(split_indices)):
            s_idx = split_indices[i]
            if 0 < s_idx < total_words:
                compound = f"{clean_word(words[s_idx - 1])} {clean_word(words[s_idx])}"
                if compound in COMMON_COMPOUND_WORDS:
                    prev_s = split_indices[i - 1] if i > 0 else 0
                    next_s = split_indices[i + 1] if i < len(split_indices) - 1 else total_words
                    if (s_idx + 1 - prev_s) <= max_words:
                        split_indices[i] = s_idx + 1
                    elif (next_s - (s_idx - 1)) <= max_words:
                        split_indices[i] = s_idx - 1

        adj_sizes = []
        prev = 0
        for idx in split_indices:
            adj_sizes.append(idx - prev)
            prev = idx
        adj_sizes.append(total_words - prev)
        
        curr_w_idx = 0
        time_per_w = total_duration / total_words
        for sz in adj_sizes:
            c_words = words[curr_w_idx : curr_w_idx + sz]
            c_text = " ".join(c_words)
            c_start = start_time + curr_w_idx * time_per_w
            c_end = start_time + (curr_w_idx + sz) * time_per_w
            if c_end > end_time or (curr_w_idx + sz) == total_words:
                c_end = end_time
            new_segments.append({"start": c_start, "end": c_end, "text": c_text})
            curr_w_idx += sz
            
    return new_segments

def split_segments_adaptive(segments, max_words=13, language=None):
    """Bộ tách phân đoạn đa ngôn ngữ thích ứng thông minh (Adaptive Multilingual Segmenter)."""
    lang = (language or "").strip().lower()
    all_chunks = []
    
    for seg in segments:
        words_data = seg.get("words", [])
        # Nếu có word_timestamps trả về từ Colab: ưu tiên sử dụng để chuẩn từng mili-giây
        if words_data and len(words_data) > 0:
            all_chunks.extend(split_segment_with_words(seg, max_words=max_words))
            continue
            
        # Nếu là tiếng Nhật hoặc Trung (không dùng dấu cách)
        if lang in ("ja", "zh"):
            cjk_chunks = split_cjk_text(seg["text"], max_chars=max(12, max_words * 2))
            if not cjk_chunks:
                continue
            total_duration = float(seg["end"]) - float(seg["start"])
            total_chars = max(1, sum(len(c) for c in cjk_chunks))
            curr_t = float(seg["start"])
            for c in cjk_chunks:
                c_dur = total_duration * (len(c) / total_chars)
                all_chunks.append({
                    "start": curr_t,
                    "end": min(float(seg["end"]), curr_t + c_dur),
                    "text": c
                })
                curr_t += c_dur
            continue
            
        # Tiếng Việt, Anh, Hàn, Tây Ban Nha, Bồ Đào Nha
        all_chunks.extend(split_segments_by_words([seg], max_words=max_words))
        
    return all_chunks


def format_timestamp_srt(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000: ms = 999
    tot = int(seconds)
    secs = tot % 60
    mins = (tot // 60) % 60
    hrs = tot // 3600
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

def export_srt_and_txt(segments, base_output_path):
    srt_path = os.path.splitext(base_output_path)[0] + ".srt"
    txt_path = os.path.splitext(base_output_path)[0] + ".txt"
    
    with open(srt_path, "w", encoding="utf-8") as f_srt:
        for idx, seg in enumerate(segments, start=1):
            s_time = format_timestamp_srt(seg["start"])
            e_time = format_timestamp_srt(seg["end"])
            txt = seg["text"].strip()
            f_srt.write(f"{idx}\n{s_time} --> {e_time}\n{txt}\n\n")
            
    with open(txt_path, "w", encoding="utf-8") as f_txt:
        for seg in segments:
            f_txt.write(f"{seg['text'].strip()}\n")
            
    return srt_path, txt_path

def insert_text_into_draft(project_path, segments, dry_run, log_callback, timeline_offset_us=0, group_subtitles=True, font_size=6.0, language="vi"):
    draft_content_path = os.path.join(project_path, "draft_content.json")
    if not os.path.exists(draft_content_path):
        raise FileNotFoundError(f"Không tìm thấy file {draft_content_path}")
        
    with open(draft_content_path, "r", encoding="utf-8") as f:
        draft_data = json.load(f)
            
    if "materials" not in draft_data: draft_data["materials"] = {}
    if "texts" not in draft_data["materials"]: draft_data["materials"]["texts"] = []
    if "tracks" not in draft_data: draft_data["tracks"] = []

    # 1. Dọn dẹp an toàn các track và vật liệu phụ đề tự động cũ do Tool tạo trước đó
    tracks_to_keep = []
    removed_mat_ids = set()
    for tr in draft_data.get("tracks", []):
        if tr.get("type") == "text":
            is_sub_track = False
            for s in tr.get("segments", []):
                mid = s.get("material_id")
                for t_mat in draft_data["materials"].get("texts", []):
                    if t_mat.get("id") == mid and (t_mat.get("type") == "subtitle" or bool(t_mat.get("group_id"))):
                        is_sub_track = True
                        break
                if is_sub_track:
                    break
            if is_sub_track:
                for s in tr.get("segments", []):
                    if s.get("material_id"):
                        removed_mat_ids.add(s["material_id"])
                continue # Bỏ track cũ này
        tracks_to_keep.append(tr)
        
    draft_data["tracks"] = tracks_to_keep
    if removed_mat_ids and "texts" in draft_data["materials"]:
        draft_data["materials"]["texts"] = [
            m for m in draft_data["materials"]["texts"] if m.get("id") not in removed_mat_ids
        ]
        
    # 2. Tạo duy nhất 1 Track text sạch sẽ
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
    locale_map = {
        "vi": "vi-VN", "en": "en-US", "ko": "ko-KR", "ja": "ja-JP",
        "es": "es-ES", "pt": "pt-PT", "pt-BR": "pt-BR", "zh": "zh-CN"
    }
    clean_lang = (language or "vi").strip()
    locale_prefix = locale_map.get(clean_lang, "vi-VN")
    shared_group_id = f"{locale_prefix}_{int(time.time() * 1000)}" if group_subtitles else ""
    font_path = get_capcut_font_path()
    fs_val = float(font_size) if font_size else 6.0
    text_size_val = int(round(fs_val * 2))
    
    for i, seg in enumerate(segments):
        start_sec = seg["start"]
        end_sec = seg["end"]
        text_content_wrapped = wrap_text(seg["text"], max_chars=40)
        start_us = int(start_sec * 1_000_000) + timeline_offset_us
        duration_us = int((end_sec - start_sec) * 1_000_000)
        if duration_us <= 0: continue
            
        text_material_id = str(uuid.uuid4()).upper()
        segment_uuid = str(uuid.uuid4()).upper()
        
        content_obj = {
            "styles": [{"fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"color": [1.0, 1.0, 1.0]}}},
                        "font": {"id": "", "path": font_path}, "range": [0, len(text_content_wrapped)], "size": fs_val, "useLetterColor": True}],
            "text": text_content_wrapped
        }
        content_json_str = json.dumps(content_obj, ensure_ascii=False)
        
        text_material = {
            "add_type": 1 if group_subtitles else 0, "alignment": 1, "base_content": content_json_str,
            "border_alpha": 1.0, "border_color": "#000000", "border_width": 0.0,
            "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "is_new": False, "path": "", "request_id": "", "resource_id": "", "resource_name": "", "third_resource_id": ""},
            "check_flag": 7, "combo_info": {"text_templates": []}, "content": content_json_str,
            "font_category_id": "", "font_category_name": "", "font_id": "", "font_name": "",
            "font_path": font_path, "font_resource_id": "", "font_size": fs_val, "font_title": "none", "font_url": "", "fonts": [],
            "global_alpha": 1.0, "group_id": shared_group_id, "has_shadow": False, "id": text_material_id, "initial_scale": 1.0, "is_rich_text": False,
            "line_feed": 1, "line_spacing": 0.02, "name": "", "operation_type": 0, "recognize_model": "", "recognize_task_id": "",
            "recognize_text": text_content_wrapped, "recognize_type": 0, "style_name": "", "sub_type": 0, "subtitle_id": text_material_id,
            "text_alpha": 1.0, "text_color": "#FFFFFF", "text_size": text_size_val, "type": "subtitle" if group_subtitles else "text", "typesetting": 0, "use_effect_default_color": False
        }
        track_segment = {
            "id": segment_uuid, "material_id": text_material_id,
            "target_timerange": {"duration": duration_us, "start": start_us}, "source_timerange": None, "render_index": 14000 + i,
            "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "transform": {"x": 0.0, "y": -0.65}, "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
            "sub_type": 0, "caption_template_info": {"category_id": "", "category_name": "", "effect_id": "", "is_new": False, "resource_id": ""}
        }
        
        if not dry_run:
            draft_data["materials"]["texts"].append(text_material)
            text_track["segments"].append(track_segment)
        inserted_count += 1
        
    if not dry_run:
        backup_path = draft_content_path + ".bak"
        shutil.copy2(draft_content_path, backup_path)
        with open(draft_content_path, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, ensure_ascii=False)
            
    return inserted_count

def find_audio_candidates(project_path):
    supported_exts = ('.mp3', '.wav', '.m4a', '.mp4', '.aac', '.flac')
    candidates = []
    draft_content_path = os.path.join(project_path, "draft_content.json")
    if not os.path.exists(draft_content_path): return candidates
    try:
        with open(draft_content_path, "r", encoding="utf-8") as f:
            draft_data = json.load(f)
        materials = draft_data.get("materials", {})
        mat_map = {}
        for cat in ["audios", "videos"]:
            for item in materials.get(cat, []):
                m_id = item.get("id")
                p = item.get("local_material_path") or item.get("path")
                if m_id and p: mat_map[m_id] = os.path.normpath(p)
                
        audios, videos = [], []
        for track in draft_data.get("tracks", []):
            t_type = track.get("type")
            for seg in track.get("segments", []):
                mat_id = seg.get("material_id")
                if mat_id and mat_id in mat_map:
                    f_path = mat_map[mat_id]
                    if os.path.exists(f_path) and f_path.lower().endswith(supported_exts):
                        t_range = seg.get("target_timerange", {})
                        s_range = seg.get("source_timerange") or {}
                        offset_us = t_range.get("start", 0) - (s_range.get("start", 0) if s_range else 0)
                        target_list = audios if t_type == "audio" else videos
                        if not any(c["path"] == f_path for c in target_list):
                            target_list.append({"path": f_path, "offset_us": offset_us})
        candidates = audios + videos
    except Exception: pass
    return candidates

def find_drafts(drafts_root):
    drafts = []
    if not drafts_root or not os.path.exists(drafts_root) or not os.path.isdir(drafts_root):
        return drafts
    try:
        for item in os.listdir(drafts_root):
            item_path = os.path.join(drafts_root, item)
            if os.path.isdir(item_path):
                content_p = os.path.join(item_path, "draft_content.json")
                meta_p = os.path.join(item_path, "draft_meta_info.json")
                if os.path.exists(content_p):
                    mtime = os.path.getmtime(content_p)
                    p_name = item
                    if os.path.exists(meta_p):
                        try:
                            with open(meta_p, "r", encoding="utf-8") as f:
                                meta_data = json.load(f)
                                p_name = meta_data.get("draft_name", item)
                                tm_mod = meta_data.get("tm_draft_modified", 0)
                                if tm_mod and tm_mod > 0:
                                    mtime = max(mtime, tm_mod / 1000000.0)
                        except Exception: pass
                    drafts.append({"name": p_name, "path": item_path, "status": "Sẵn sàng (Ready)", "mtime": mtime})
        # Sắp xếp từ mới nhất xuống cũ nhất
        drafts.sort(key=lambda d: d.get("mtime", 0), reverse=True)
    except Exception: pass
    return drafts

# ==============================================================================
# PHẦN 4: GIAO DIỆN HIỆN ĐẠI BATCH STUDIO (Tkinter Modern UI)
# ==============================================================================

class CapCutBatchStudioApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("CapCut Audio to Text Tool - Google Colab Tesla T4 (Batch Studio)")
        
        # Bảng màu Dark Studio cao cấp (lấy cảm hứng từ Tool Chia Segment)
        self.bg_main = "#0B0F19"
        self.bg_card = "#1E293B"
        self.bg_card_inner = "#0F172A"
        self.fg_main = "#F8FAFC"
        self.fg_dim = "#94A3B8"
        self.accent_cyan = "#38BDF8"
        self.accent_blue = "#2563EB"
        self.accent_green = "#34D399"
        self.accent_orange = "#FB923C"
        self.accent_red = "#EF4444"
        self.btn_bg = "#334155"
        
        self.configure(bg=self.bg_main)
        self.config = self._load_config()
        
        # Biến cấu hình
        self.var_colab_url = tk.StringVar(value="")
        self.var_colab_status = tk.StringVar(value="• Chưa kết nối Colab")
        self.var_drafts_dir = tk.StringVar(value=self.config.get("drafts_dir", ""))
        self.var_language = tk.StringVar(value=self.config.get("language", "Tự động nhận diện"))
        self.var_max_words = tk.IntVar(value=self.config.get("max_words", 13))
        self.var_font_size = tk.DoubleVar(value=self.config.get("font_size", 6.0))
        self.var_group_sub = tk.BooleanVar(value=self.config.get("group_subtitles", True))
        self.var_output_dir = tk.StringVar(value=self.config.get("output_dir", ""))
        
        # Danh sách hàng đợi dự án CapCut
        # Mỗi item: {"id": str, "name": str, "path": str, "status": str}
        self.queue_items = []
        self.stop_event = threading.Event()
        self.is_processing = False
        
        self.lang_map = {
            "Tự động nhận diện": None,
            "Tiếng Việt (vi)": "vi",
            "Tiếng Hàn (ko)": "ko",
            "Tiếng Nhật (ja)": "ja",
            "Tiếng Anh (en)": "en",
            "Tiếng Tây Ban Nha (es)": "es",
            "Tiếng Bồ Đào Nha (pt)": "pt",
            "Tiếng Bồ Đào Nha - Brazil (pt-BR)": "pt-BR",
            "Tiếng Trung (zh)": "zh"
        }
        
        self._init_styles()
        self._create_widgets()
        self._center_window()
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        if self.var_drafts_dir.get():
            self.after(300, self._refresh_drafts_list)


    def _center_window(self):
        """
        Tự động tính toán kích thước Studio và tọa độ để cửa sổ luôn nằm ở chính giữa màn hình Windows,
        tương thích hoàn hảo với mọi độ phân giải và tỉ lệ Windows Display Scaling.
        """
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        
        # Studio Size: ~1440 x 950 px trên Full HD, hoặc ~95% chiều rộng & ~94% chiều cao màn hình khả dụng
        win_w = min(1440, int(screen_w * 0.95))
        win_h = min(950, int((screen_h - 45) * 0.94))
        
        x = max(0, (screen_w - win_w) // 2)
        y = max(15, (screen_h - win_h - 45) // 2)
        
        self.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.minsize(1050, 680)

    def _init_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        # Cấu hình Treeview
        self.style.configure("Studio.Treeview", 
                             background=self.bg_card_inner, 
                             foreground=self.fg_main, 
                             fieldbackground=self.bg_card_inner,
                             rowheight=28,
                             font=("Segoe UI", 9))
        self.style.map("Studio.Treeview", 
                       background=[("selected", self.accent_blue)], 
                       foreground=[("selected", "#FFFFFF")])
        self.style.configure("Studio.Treeview.Heading", 
                             background=self.btn_bg, 
                             foreground=self.accent_cyan, 
                             font=("Segoe UI", 9, "bold"),
                             borderwidth=1)
                             
        # Cấu hình TCombobox đồng bộ Dark Theme cao cấp
        self.style.configure("TCombobox", 
                             fieldbackground=self.bg_card_inner, 
                             background=self.btn_bg, 
                             foreground=self.fg_main, 
                             arrowcolor=self.accent_cyan,
                             darkcolor=self.bg_card, 
                             lightcolor=self.bg_card)
        self.style.map("TCombobox", 
                       fieldbackground=[("readonly", self.bg_card_inner)], 
                       foreground=[("readonly", self.fg_main)],
                       selectbackground=[("readonly", self.accent_blue)],
                       selectforeground=[("readonly", "#FFFFFF")])
        
        # Cấu hình Dropdown Listbox của Combobox
        self.option_add("*TCombobox*Listbox.background", self.bg_card_inner)
        self.option_add("*TCombobox*Listbox.foreground", self.fg_main)
        self.option_add("*TCombobox*Listbox.selectBackground", self.accent_blue)
        self.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
        self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))

    def _bind_hover(self, btn, normal_bg, hover_bg):
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg) if str(btn["state"]) != "disabled" else None)
        btn.bind("<Leave>", lambda e: btn.configure(bg=normal_bg) if str(btn["state"]) != "disabled" else None)

    def _create_widgets(self):
        # 1. TOP HEADER & COLAB BAR (Thanh công cụ kết nối & Copy Code)
        top_bar = tk.Frame(self, bg=self.bg_card, bd=1, relief=tk.SOLID, padx=14, pady=8)
        top_bar.pack(fill=tk.X, padx=12, pady=(8, 6))
        
        # Hàng 1: Tiêu đề
        row_title = tk.Frame(top_bar, bg=self.bg_card)
        row_title.pack(fill=tk.X, pady=(0, 6))
        
        tk.Label(row_title, text="🎙️ CAPCUT AUDIO TO TEXT", font=("Segoe UI", 15, "bold"), fg=self.accent_cyan, bg=self.bg_card).pack(side=tk.LEFT)
        tk.Label(row_title, text="• GOOGLE COLAB TESLA T4 16GB (BATCH STUDIO)", font=("Segoe UI", 10, "bold"), fg=self.accent_green, bg=self.bg_card).pack(side=tk.LEFT, padx=(8, 0))
        
        # Hàng 2: Nhập Link Colab, Kết nối, Copy Code, Mở Colab
        row_conn = tk.Frame(top_bar, bg=self.bg_card)
        row_conn.pack(fill=tk.X)
        
        tk.Label(row_conn, text="Link Colab:", font=("Segoe UI", 9, "bold"), fg=self.fg_main, bg=self.bg_card).pack(side=tk.LEFT, padx=(0, 6))
        
        self.entry_colab = tk.Entry(row_conn, textvariable=self.var_colab_url, font=("Consolas", 10), bg=self.bg_card_inner, fg="#FFFFFF",
                                    insertbackground="#FFFFFF", bd=1, relief=tk.SOLID)
        self.entry_colab.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)
        
        self.btn_connect = tk.Button(row_conn, text="🔗 Kết nối", font=("Segoe UI", 9, "bold"), bg=self.accent_cyan, fg="#0F172A",
                                     activebackground="#7dd3fc", activeforeground="#0F172A", bd=0, padx=12, pady=3, cursor="hand2", command=self._test_colab_connection)
        self.btn_connect.pack(side=tk.LEFT, padx=(0, 8))
        self._bind_hover(self.btn_connect, self.accent_cyan, "#7dd3fc")
        
        self.lbl_colab_status = tk.Label(row_conn, textvariable=self.var_colab_status, font=("Segoe UI", 9, "bold"), fg=self.fg_dim, bg=self.bg_card)
        self.lbl_colab_status.pack(side=tk.LEFT, padx=(0, 10))
        
        # Nút 1-Click Copy Code Colab
        self.btn_copy_code = tk.Button(row_conn, text="📋 Copy Code Colab", font=("Segoe UI", 9, "bold"), bg="#1E1B4B", fg=self.accent_cyan,
                                       activebackground="#312E81", activeforeground="#FFFFFF", bd=1, relief=tk.SOLID, padx=12, pady=3,
                                       cursor="hand2", command=self._quick_copy_colab_code)
        self.btn_copy_code.pack(side=tk.RIGHT, padx=(4, 0))
        self._bind_hover(self.btn_copy_code, "#1E1B4B", "#312E81")
        


        # 2. KHU VỰC LÀM VIỆC CHÍNH (BỐ CỤC 2 CỘT GRID VỮNG CHẮC)
        work_container = tk.Frame(self, bg=self.bg_main)
        work_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 8))
        work_container.columnconfigure(0, weight=1, uniform="work_col")
        work_container.columnconfigure(1, weight=1, uniform="work_col")
        work_container.rowconfigure(0, weight=1)
        
        # -------------------------------------------------------------
        # CỘT TRÁI: HÀNG ĐỢI DỰ ÁN CAPCUT & CẤU HÌNH PHỤ ĐỀ
        # -------------------------------------------------------------
        left_frame = tk.Frame(work_container, bg=self.bg_main)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        
        # Card 1: Hàng đợi dự án CapCut
        card_queue = tk.LabelFrame(left_frame, text="1. Hàng Đợi Dự Án CapCut Cần Xử Lý (Batch Queue)", bg=self.bg_card, fg=self.accent_cyan,
                                   font=("Segoe UI", 10, "bold"), padx=10, pady=6, bd=1, relief=tk.SOLID)
        card_queue.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        
        # Toolbar của hàng đợi
        q_toolbar = tk.Frame(card_queue, bg=self.bg_card)
        q_toolbar.pack(fill=tk.X, pady=(0, 5))
        
        btn_remove_item = tk.Button(q_toolbar, text="🗑️ Xóa Mục Chọn", font=("Segoe UI", 8, "bold"), bg=self.btn_bg, fg=self.fg_main,
                                    activebackground=self.accent_red, bd=0, padx=9, pady=3, cursor="hand2", command=self._remove_queue_item)
        btn_remove_item.pack(side=tk.LEFT, padx=(0, 6))
        self._bind_hover(btn_remove_item, self.btn_bg, self.accent_red)
        
        btn_clear_all = tk.Button(q_toolbar, text="🔄 Xóa Hết Hàng Đợi", font=("Segoe UI", 8), bg=self.btn_bg, fg=self.fg_main,
                                  activebackground="#7f1d1d", bd=0, padx=9, pady=3, cursor="hand2", command=self._clear_queue)
        btn_clear_all.pack(side=tk.LEFT)
        self._bind_hover(btn_clear_all, self.btn_bg, "#7f1d1d")
        
        self.lbl_queue_count = tk.Label(q_toolbar, text="0 dự án", font=("Segoe UI", 8, "bold"), bg="#1E1B4B", fg=self.accent_cyan, padx=10, pady=2, bd=1, relief=tk.SOLID)
        self.lbl_queue_count.pack(side=tk.RIGHT)
        
        # Bảng Treeview của hàng đợi (Cột: #, Tên Dự Án CapCut, Trạng Thái)
        tree_q_container = tk.Frame(card_queue, bg=self.bg_card_inner, bd=1, relief=tk.SOLID)
        tree_q_container.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        
        q_cols = ("#", "name", "status")
        self.tree_queue = ttk.Treeview(tree_q_container, columns=q_cols, show="headings", style="Studio.Treeview", selectmode="extended", height=10)
        self.tree_queue.heading("#", text="#")
        self.tree_queue.heading("name", text="Tên Dự Án CapCut (Draft Name)")
        self.tree_queue.heading("status", text="Trạng Thái Xử Lý")
        
        self.tree_queue.column("#", width=38, anchor=tk.CENTER)
        self.tree_queue.column("name", width=360, anchor=tk.W)
        self.tree_queue.column("status", width=180, anchor=tk.W)
        
        q_scroll = ttk.Scrollbar(tree_q_container, orient=tk.VERTICAL, command=self.tree_queue.yview)
        self.tree_queue.configure(yscrollcommand=q_scroll.set)
        self.tree_queue.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        q_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree_queue.tag_configure("waiting", foreground="#94A3B8")
        self.tree_queue.tag_configure("processing", foreground=self.accent_cyan)
        self.tree_queue.tag_configure("completed", foreground=self.accent_green)
        self.tree_queue.tag_configure("failed", foreground=self.accent_red)
        
        # Card 2: Cấu hình phụ đề & Master Action
        card_sub_opts = tk.LabelFrame(left_frame, text="2. Cấu hình Phụ Đề & Hành Động", bg=self.bg_card, fg=self.accent_cyan,
                                      font=("Segoe UI", 10, "bold"), padx=10, pady=6, bd=1, relief=tk.SOLID)
        card_sub_opts.pack(fill=tk.X)
        
        row_cfg = tk.Frame(card_sub_opts, bg=self.bg_card)
        row_cfg.pack(fill=tk.X, pady=(0, 4))
        
        tk.Label(row_cfg, text="Ngôn ngữ voice:", font=("Segoe UI", 9), fg=self.fg_main, bg=self.bg_card).grid(row=0, column=0, sticky=tk.W, pady=2)
        cb_lang = ttk.Combobox(row_cfg, textvariable=self.var_language, values=list(self.lang_map.keys()), state="readonly", width=22, font=("Segoe UI", 9))
        cb_lang.grid(row=0, column=1, sticky=tk.W, padx=6, pady=2)
        
        tk.Label(row_cfg, text="Giới hạn từ:", font=("Segoe UI", 9), fg=self.fg_main, bg=self.bg_card).grid(row=0, column=2, sticky=tk.W, padx=(8, 0), pady=2)
        sb_words = tk.Spinbox(row_cfg, from_=1, to=100, textvariable=self.var_max_words, width=5, bg=self.bg_card_inner, fg=self.fg_main, bd=1, relief=tk.SOLID, font=("Segoe UI", 9))
        sb_words.grid(row=0, column=3, sticky=tk.W, padx=4, pady=2)
        
        tk.Label(row_cfg, text="Cỡ chữ:", font=("Segoe UI", 9), fg=self.fg_main, bg=self.bg_card).grid(row=0, column=4, sticky=tk.W, padx=(8, 0), pady=2)
        sb_font_size = tk.Spinbox(row_cfg, from_=1.0, to=30.0, increment=0.5, textvariable=self.var_font_size, width=5, bg=self.bg_card_inner, fg=self.fg_main, bd=1, relief=tk.SOLID, font=("Segoe UI", 9))
        sb_font_size.grid(row=0, column=5, sticky=tk.W, padx=4, pady=2)
        
        # Chế độ phụ đề CapCut
        row_mode = tk.Frame(card_sub_opts, bg=self.bg_card)
        row_mode.pack(fill=tk.X, pady=(2, 5))
        
        tk.Label(row_mode, text="Kiểu phụ đề CapCut:", font=("Segoe UI", 9, "bold"), fg=self.fg_main, bg=self.bg_card).pack(side=tk.LEFT, padx=(0, 10))
        r_group = tk.Radiobutton(row_mode, text="Nhóm Sub (Áp dụng cho tất cả)", variable=self.var_group_sub, value=True,
                                 bg=self.bg_card, fg=self.accent_green, activebackground=self.bg_card, selectcolor=self.bg_card_inner, font=("Segoe UI", 9))
        r_group.pack(side=tk.LEFT, padx=(0, 12))
        
        r_nogroup = tk.Radiobutton(row_mode, text="Văn bản độc lập", variable=self.var_group_sub, value=False,
                                   bg=self.bg_card, fg=self.accent_orange, activebackground=self.bg_card, selectcolor=self.bg_card_inner, font=("Segoe UI", 9))
        r_nogroup.pack(side=tk.LEFT)
        
        # Nút Master hành động chạy hàng đợi
        row_action = tk.Frame(card_sub_opts, bg=self.bg_card)
        row_action.pack(fill=tk.X, pady=(4, 2))
        
        self.btn_run_batch = tk.Button(row_action, text="⚡ BẮT ĐẦU CHẠY HÀNG CHỜ (BATCH PROCESS)", font=("Segoe UI", 11, "bold"),
                                       bg=self.accent_cyan, fg="#0F172A", activebackground="#7dd3fc", activeforeground="#0F172A",
                                       bd=0, pady=8, cursor="hand2", command=self._start_batch_pipeline)
        self.btn_run_batch.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self._bind_hover(self.btn_run_batch, self.accent_cyan, "#7dd3fc")
        
        self.btn_stop_batch = tk.Button(row_action, text="⏹️ Dừng", font=("Segoe UI", 10, "bold"),
                                        bg=self.btn_bg, fg=self.accent_red, activebackground=self.accent_red, activeforeground="#FFFFFF",
                                        bd=0, pady=8, width=8, cursor="hand2", state=tk.DISABLED, command=self._stop_batch_pipeline)
        self.btn_stop_batch.pack(side=tk.RIGHT)
        self._bind_hover(self.btn_stop_batch, self.btn_bg, self.accent_red)

        # -------------------------------------------------------------
        # CỘT PHẢI: DỰ ÁN CAPCUT & OUTPUT LOG
        # -------------------------------------------------------------
        right_frame = tk.Frame(work_container, bg=self.bg_main)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        
        # Card 3: Danh sách dự án CapCut
        card_drafts = tk.LabelFrame(right_frame, text="3. Thư Mục Dự Án CapCut Trên Máy", bg=self.bg_card, fg=self.accent_cyan,
                                    font=("Segoe UI", 10, "bold"), padx=10, pady=6, bd=1, relief=tk.SOLID)
        card_drafts.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        
        # Thư mục Drafts
        row_draft_p = tk.Frame(card_drafts, bg=self.bg_card)
        row_draft_p.pack(fill=tk.X, pady=(0, 4))
        
        tk.Label(row_draft_p, text="Thư mục:", font=("Segoe UI", 9), fg=self.fg_main, bg=self.bg_card).pack(side=tk.LEFT, padx=(0, 6))
        entry_draft_p = tk.Entry(row_draft_p, textvariable=self.var_drafts_dir, font=("Segoe UI", 9), bg=self.bg_card_inner, fg=self.fg_main,
                                 insertbackground=self.fg_main, bd=1, relief=tk.SOLID)
        entry_draft_p.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=2)
        
        btn_br_drafts = tk.Button(row_draft_p, text="Browse...", font=("Segoe UI", 8), bg=self.btn_bg, fg=self.fg_main, bd=0, padx=8, pady=2, cursor="hand2", command=self._browse_drafts_dir)
        btn_br_drafts.pack(side=tk.LEFT, padx=(0, 4))
        self._bind_hover(btn_br_drafts, self.btn_bg, "#475569")
        
        btn_rf_drafts = tk.Button(row_draft_p, text="🔄 Làm mới", font=("Segoe UI", 8, "bold"), bg=self.btn_bg, fg=self.accent_cyan, bd=0, padx=8, pady=2, cursor="hand2", command=self._refresh_drafts_list)
        btn_rf_drafts.pack(side=tk.LEFT)
        self._bind_hover(btn_rf_drafts, self.btn_bg, "#475569")
        
        # Treeview danh sách dự án
        tree_d_container = tk.Frame(card_drafts, bg=self.bg_card_inner, bd=1, relief=tk.SOLID)
        tree_d_container.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        
        d_cols = ("name", "status")
        self.tree_drafts = ttk.Treeview(tree_d_container, columns=d_cols, show="headings", style="Studio.Treeview", selectmode="extended", height=10)
        self.tree_drafts.heading("name", text="Tên Dự Án CapCut (Draft Name)")
        self.tree_drafts.heading("status", text="Trạng Thái")
        self.tree_drafts.column("name", width=340, anchor=tk.W)
        self.tree_drafts.column("status", width=140, anchor=tk.CENTER)
        
        d_scroll = ttk.Scrollbar(tree_d_container, orient=tk.VERTICAL, command=self.tree_drafts.yview)
        self.tree_drafts.configure(yscrollcommand=d_scroll.set)
        self.tree_drafts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        d_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Nút đẩy dự án được chọn vào hàng đợi
        btn_add_project_to_queue = tk.Button(card_drafts, text="➕ ĐƯA DỰ ÁN ĐÃ CHỌN VÀO HÀNG ĐỢI (QUEUE)", font=("Segoe UI", 9, "bold"),
                                             bg=self.btn_bg, fg=self.accent_green, activebackground="#059669", activeforeground="#FFFFFF",
                                             bd=1, relief=tk.SOLID, pady=4, cursor="hand2", command=self._add_selected_drafts_to_queue)
        btn_add_project_to_queue.pack(fill=tk.X)
        self._bind_hover(btn_add_project_to_queue, self.btn_bg, "#065f46")
        
        # Card 4: Output Log & Progress Bar
        card_log = tk.LabelFrame(right_frame, text="4. Tiến Trình & Nhật Ký (Live Output Log)", bg=self.bg_card, fg=self.accent_cyan,
                                 font=("Segoe UI", 10, "bold"), padx=10, pady=6, bd=1, relief=tk.SOLID)
        card_log.pack(fill=tk.BOTH, expand=True)
        
        # Thanh tiến trình & trạng thái
        prog_row = tk.Frame(card_log, bg=self.bg_card)
        prog_row.pack(fill=tk.X, pady=(0, 6))
        
        self.lbl_progress_status = tk.Label(prog_row, text="Sẵn sàng thực hiện", font=("Segoe UI", 9, "bold"), fg=self.fg_dim, bg=self.bg_card)
        self.lbl_progress_status.pack(side=tk.LEFT)
        
        self.lbl_elapsed_timer = tk.Label(prog_row, text="00:00", font=("Consolas", 10, "bold"), fg=self.accent_orange, bg=self.bg_card)
        self.lbl_elapsed_timer.pack(side=tk.RIGHT)
        
        self.prog_bar = ttk.Progressbar(card_log, orient=tk.HORIZONTAL, mode="determinate")
        self.prog_bar.pack(fill=tk.X, pady=(0, 6))
        
        # Console text area
        log_container = tk.Frame(card_log, bg=self.bg_card_inner, bd=1, relief=tk.SOLID)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        self.txt_log = tk.Text(log_container, bg=self.bg_card_inner, fg=self.fg_main, insertbackground=self.fg_main,
                               wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED, bd=0)
        log_scroll = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scroll.set)
        
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log("Khởi động CapCut Batch Studio thành công!")
        self.log("Mẹo: Bấm '📋 Copy Code Colab' để lấy mã nguồn chạy trên Google Colab T4 16GB.")

    # ==========================================================================
    # CÁC HÀM XỬ LÝ HÀNG ĐỢI (BATCH QUEUE ACTIONS)
    # ==========================================================================

    def log(self, message):
        """Thread-safe logging vào console text area"""
        def _ui_log():
            timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
            self.txt_log.configure(state=tk.NORMAL)
            self.txt_log.insert(tk.END, f"{timestamp} {message}\n")
            self.txt_log.see(tk.END)
            self.txt_log.configure(state=tk.DISABLED)
        self.after(0, _ui_log)

    def _quick_copy_colab_code(self):
        try:
            code = get_colab_run_code()
            self.clipboard_clear()
            self.clipboard_append(code)
            self.update()
            self.btn_copy_code.configure(text="✅ Đã Copy!", bg="#059669", fg="#FFFFFF")
            self.log("[COPY THÀNH CÔNG] Toàn bộ mã nguồn Colab đã được lưu vào Clipboard!")
            self.after(2500, self._reset_copy_btn)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể sao chép code: {e}")

    def _reset_copy_btn(self):
        try:
            self.btn_copy_code.configure(text="📋 Copy Code Colab", bg="#1E1B4B", fg=self.accent_cyan)
        except Exception: pass

    def _test_colab_connection(self):
        url = self.var_colab_url.get().strip()
        if not url:
            self.var_colab_status.set("• Chưa nhập link Colab!")
            self.lbl_colab_status.configure(fg=self.accent_red)
            return
            
        self.var_colab_status.set("• Đang kiểm tra...")
        self.lbl_colab_status.configure(fg=self.accent_cyan)
        self._save_config()
        
        def run_test():
            ok, msg = check_colab_health(url)
            def _update_ui():
                if ok:
                    self.var_colab_status.set(f"● {msg}")
                    self.lbl_colab_status.configure(fg=self.accent_green)
                    self.log(f"[KẾT NỐI COLAB THÀNH CÔNG] {msg}")
                else:
                    self.var_colab_status.set(f"● {msg}")
                    self.lbl_colab_status.configure(fg=self.accent_red)
                    self.log(f"[LỖI KẾT NỐI COLAB] {msg}")
            self.after(0, _update_ui)
                
        threading.Thread(target=run_test, daemon=True).start()

    def _add_selected_drafts_to_queue(self):
        selected_ids = self.tree_drafts.selection()
        if not selected_ids:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn ít nhất 1 dự án trong danh sách CapCut bên dưới!")
            return
            
        added = 0
        for s_id in selected_ids:
            tags = self.tree_drafts.item(s_id, "tags")
            vals = self.tree_drafts.item(s_id, "values")
            if tags and tags[0] != "scanning":
                d_path = tags[0]
                d_name = vals[0]
                if not any(item["path"] == d_path for item in self.queue_items):
                    item_id = str(uuid.uuid4())[:8]
                    self.queue_items.append({
                        "id": item_id,
                        "name": d_name,
                        "path": d_path,
                        "status": "Chờ xử lý"
                    })
                    idx = len(self.queue_items)
                    self.tree_queue.insert("", tk.END, iid=item_id, values=(idx, d_name, "⏳ Chờ xử lý"), tags=("waiting",))
                    added += 1
                    
        self._update_queue_badge()
        self.log(f"Đã thêm {added} dự án CapCut vào hàng đợi.")

    def _remove_queue_item(self):
        selected_ids = self.tree_queue.selection()
        if not selected_ids: return
        for s_id in selected_ids:
            self.queue_items = [item for item in self.queue_items if item["id"] != s_id]
            self.tree_queue.delete(s_id)
        self._reindex_queue()
        self._update_queue_badge()

    def _clear_queue(self):
        if self.is_processing:
            messagebox.showwarning("Cảnh báo", "Đang có tiến trình xử lý hàng đợi, không thể xóa!")
            return
        self.queue_items.clear()
        for item in self.tree_queue.get_children():
            self.tree_queue.delete(item)
        self._update_queue_badge()
        self.log("Đã dọn sạch hàng đợi.")

    def _reindex_queue(self):
        for idx, item in enumerate(self.queue_items, start=1):
            s_id = item["id"]
            cur_vals = self.tree_queue.item(s_id, "values")
            status = cur_vals[2] if len(cur_vals) > 2 else "⏳ Chờ xử lý"
            self.tree_queue.item(s_id, values=(idx, item["name"], status))

    def _update_queue_badge(self):
        count = len(self.queue_items)
        self.lbl_queue_count.configure(text=f"{count} dự án")

    # ==========================================================================
    # CÁC HÀM XỬ LÝ DỰ ÁN CAPCUT
    # ==========================================================================

    def _browse_drafts_dir(self):
        p = filedialog.askdirectory(title="Chọn thư mục Drafts của CapCut")
        if p:
            self.var_drafts_dir.set(p)
            self._save_config()
            self._refresh_drafts_list()

    def _refresh_drafts_list(self):
        root_dir = self.var_drafts_dir.get().strip()
        if not root_dir: return
        
        for item in self.tree_drafts.get_children():
            self.tree_drafts.delete(item)
        self.tree_drafts.insert("", tk.END, values=("Đang quét dự án CapCut...", "Vui lòng chờ..."), tags=("scanning",))
        
        def _scan_worker():
            drafts = find_drafts(root_dir)
            def _update_tree():
                for item in self.tree_drafts.get_children():
                    self.tree_drafts.delete(item)
                for d in drafts:
                    self.tree_drafts.insert("", tk.END, values=(d["name"], d["status"]), tags=(d["path"],))
                self.log(f"Đã quét danh sách dự án CapCut: Tìm thấy {len(drafts)} dự án.")
            self.after(0, _update_tree)
            
        threading.Thread(target=_scan_worker, daemon=True).start()

    def _is_capcut_running(self):
        try:
            import subprocess
            out = subprocess.check_output('tasklist', shell=True).decode('utf-8', errors='ignore').lower()
            return "capcut" in out
        except Exception: return False

    # ==========================================================================
    # BATCH QUEUE PIPELINE WORKER (THREAD-SAFE)
    # ==========================================================================

    def _start_batch_pipeline(self):
        if not self.queue_items:
            messagebox.showwarning("Hàng đợi trống", "Vui lòng chọn và đưa ít nhất 1 dự án CapCut vào hàng đợi!")
            return
            
        colab_url = self.var_colab_url.get().strip()
        if not colab_url or not colab_url.startswith("http"):
            messagebox.showerror("Chưa có link Colab", "Vui lòng dán Link Cloudflare Colab (https://xxxx.trycloudflare.com) và bấm Kết nối trước!")
            return

        if self._is_capcut_running():
            proceed = messagebox.askokcancel(
                "Lưu ý quan trọng",
                "Phần mềm CapCut hiện đang mở trên máy.\n\n"
                "QUAN TRỌNG: Bạn CẦN quay ra màn hình Trang chủ (Homepage) của CapCut hoặc đóng CapCut lại trước khi chạy hàng đợi.\n"
                "Nếu để mở màn hình chỉnh sửa dự án, CapCut sẽ tự động ghi đè làm mất phụ đề mới.\n\n"
                "Bạn đã quay ra Trang chủ và muốn tiếp tục?"
            )
            if not proceed: return

        self.stop_event.clear()
        self.is_processing = True
        self.btn_run_batch.configure(state=tk.DISABLED, text="⚡ ĐANG XỬ LÝ HÀNG ĐỢI...")
        self.btn_stop_batch.configure(state=tk.NORMAL)
        
        threading.Thread(target=self._run_batch_worker, args=(colab_url,), daemon=True).start()

    def _stop_batch_pipeline(self):
        if messagebox.askyesno("Xác nhận dừng", "Bạn có chắc chắn muốn dừng hàng đợi sau khi dự án hiện tại kết thúc?"):
            self.stop_event.set()
            self.log("[CẢNH BÁO] Đã nhận lệnh dừng hàng đợi...")

    def _run_batch_worker(self, colab_url):
        total_items = len(self.queue_items)
        language_display = self.var_language.get()
        language_code = self.lang_map.get(language_display)
        max_words = self.var_max_words.get()
        font_size = self.var_font_size.get()
        group_sub = self.var_group_sub.get()
        
        def _safe_update(fn):
            self.after(0, fn)
            
        _safe_update(lambda: [
            self.prog_bar.configure(maximum=total_items, value=0)
        ])
        start_batch_time = time.time()
        
        self.log("=" * 65)
        self.log(f"KHỞI ĐỘNG XỬ LÝ HÀNG ĐỢI ({total_items} DỰ ÁN CAPCUT):")
        self.log(f"  Colab GPU: {colab_url}")
        self.log(f"  Ngôn ngữ: {language_display} | Tối đa từ/đoạn: {max_words}")
        self.log("=" * 65)
        
        completed_count = 0
        failed_count = 0
        
        for idx, item in enumerate(self.queue_items, start=1):
            if self.stop_event.is_set():
                self.log("[DỪNG LẠI] Hàng đợi đã bị hủy bởi người dùng.")
                break
                
            item_id = item["id"]
            name = item["name"]
            path = item["path"]
            
            # Cập nhật trạng thái item đang chạy (Thread-safe)
            _safe_update(lambda i=item_id, n=name, ix=idx: [
                self.tree_queue.item(i, values=(ix, n, "⚡ Đang xử lý..."), tags=("processing",)),
                self.lbl_progress_status.configure(text=f"Đang xử lý [{ix}/{total_items}]: {n}", fg=self.accent_cyan)
            ])
            
            item_start_t = time.time()
            self.log(f"\n---> [{idx}/{total_items}] Bắt đầu: {name}")
            
            try:
                # 1. Tìm audio/video trên timeline của dự án CapCut
                candidates = find_audio_candidates(path)
                if not candidates:
                    raise FileNotFoundError("Không tìm thấy tệp audio/video nào trên timeline của dự án này!")
                audio_target = candidates[0]["path"]
                offset_us = candidates[0]["offset_us"]
                    
                # 2. Gửi sang Colab Large-v3 GPU
                raw_segments = transcribe_audio_colab(colab_url, audio_target, language_code, self.log, stop_event=self.stop_event)
                
                # 3. Bộ lọc ảo giác & vòng lặp từ vô tận (Anti-Hallucination)
                filtered_segments = filter_hallucinations_and_loops(raw_segments, language=language_code)
                if len(filtered_segments) < len(raw_segments):
                    self.log(f"  -> Đã lọc bỏ {len(raw_segments) - len(filtered_segments)} đoạn ảo giác / lặp từ rác!")
                
                # 4. Tách đoạn thông minh thích ứng theo ngôn ngữ & Word Timestamps chuẩn xác
                segments = split_segments_adaptive(filtered_segments, max_words=max_words, language=language_code)
                
                # 5. Khử đè layer (Đảm bảo 100% không trùng mốc thời gian, duy trì 1 Track duy nhất)
                final_segments = reconcile_segment_overlaps(segments)
                
                # 6. Ghi trực tiếp vào draft_content.json của CapCut (chuẩn Cỡ chữ & dọn sạch track cũ)
                inserted = insert_text_into_draft(
                    path, final_segments, dry_run=False, log_callback=self.log,
                    timeline_offset_us=offset_us, group_subtitles=group_sub,
                    font_size=font_size, language=language_code
                )
                self.log(f"  -> Đã chèn {inserted} đoạn phụ đề (Cỡ chữ: {font_size}) vào duy nhất 1 Track CapCut!")
                
                # 7. Tự động xuất file .srt và .txt trong thư mục dự án
                try:
                    srt_p, txt_p = export_srt_and_txt(final_segments, os.path.join(path, f"{name}_subtitle"))
                    self.log(f"  -> Đã xuất file phụ đề: {os.path.basename(srt_p)}")
                except Exception:
                    pass
                
                dur_item = round(time.time() - item_start_t, 1)
                _safe_update(lambda i=item_id, n=name, ix=idx, d=dur_item: [
                    self.tree_queue.item(i, values=(ix, n, f"✅ Hoàn thành ({d}s)"), tags=("completed",))
                ])
                completed_count += 1
                
            except Exception as e:
                dur_item = round(time.time() - item_start_t, 1)
                _safe_update(lambda i=item_id, n=name, ix=idx: [
                    self.tree_queue.item(i, values=(ix, n, "❌ Thất bại"), tags=("failed",))
                ])
                self.log(f"  [LỖI] Xử lý dự án {name} thất bại: {e}")
                failed_count += 1
                
            elapsed_tot = int(time.time() - start_batch_time)
            mins, secs = elapsed_tot // 60, elapsed_tot % 60
            _safe_update(lambda ix=idx, m=mins, s=secs: [
                self.prog_bar.configure(value=ix),
                self.lbl_elapsed_timer.configure(text=f"{m:02d}:{s:02d}")
            ])
            
        total_time = round(time.time() - start_batch_time, 1)
        self.log("\n" + "=" * 65)
        self.log(f"HOÀN TẤT HÀNG ĐỢI! Thành công: {completed_count}/{total_items} | Lỗi: {failed_count} | Tổng thời gian: {total_time}s")
        self.log("=" * 65)
        
        def _finish_ui():
            self.lbl_progress_status.configure(text=f"Hoàn thành ({completed_count}/{total_items} dự án)", fg=self.accent_green)
            self.btn_run_batch.configure(state=tk.NORMAL, text="⚡ BẮT ĐẦU CHẠY HÀNG CHỜ (BATCH PROCESS)")
            self.btn_stop_batch.configure(state=tk.DISABLED)
            self.is_processing = False
            messagebox.showinfo("Hoàn thành", f"Đã chạy xong hàng đợi!\nThành công: {completed_count}/{total_items}\nLỗi: {failed_count}\nThời gian: {total_time} giây.")
        _safe_update(_finish_ui)

    def _load_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        default_config = {
            "colab_url": "",
            "drafts_dir": get_default_drafts_dir(),
            "language": "Tự động nhận diện",
            "max_words": 13,
            "font_size": 6.0,
            "group_subtitles": True,
            "auto_export_srt": True,
            "output_dir": ""
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    default_config.update(saved)
            except Exception: pass
        default_config["colab_url"] = "" # Luôn làm mới link Colab
        if not default_config.get("drafts_dir"):
            default_config["drafts_dir"] = get_default_drafts_dir()
        return default_config

    def _save_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
        try:
            config_data = {
                "colab_url": "", # Không lưu URL Colab để phiên sau luôn mới
                "drafts_dir": self.var_drafts_dir.get(),
                "language": self.var_language.get(),
                "max_words": int(self.var_max_words.get()),
                "font_size": float(self.var_font_size.get()),
                "group_subtitles": bool(self.var_group_sub.get()),
                "auto_export_srt": True,
                "output_dir": self.var_output_dir.get()
            }
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception: pass

    def _on_close(self):
        self._save_config()
        self.destroy()


if __name__ == "__main__":
    app = CapCutBatchStudioApp()
    app.mainloop()
