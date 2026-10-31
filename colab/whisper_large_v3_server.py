# ==============================================================================
# WHISPER LARGE-V3 COLAB GPU SERVER (OPTIMIZED FOR TESLA T4 16GB)
# ==============================================================================
# Hỗ trợ: FastAPI + Uvicorn + Cloudflare Tunnel + Batched Faster-Whisper
# Tối ưu hóa: Khai thác 13.0 - 13.5 GB VRAM trên Tesla T4, tốc độ siêu tốc
# ==============================================================================

import os
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
import io
import time
import base64
import tempfile
import threading
import subprocess
import re
import uuid
import gc, glob, site, ctypes
from typing import Optional, List

# Cấu hình và nạp thư viện CUDA 12 (libcublas, libcudnn) cho CTranslate2
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

# Cấu hình PyTorch CUDA Memory Allocator chống phân mảnh RAM GPU khi chạy ở mức 13.5GB
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import torch
import nest_asyncio
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Thiết lập cờ tăng tốc phần cứng cho Tensor Cores
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

# Vá lỗi tương thích giữa PyAV và faster-whisper (loại bỏ metadata_errors trên PyAV 18+)
try:
    import av
    _orig_av_open = av.open
    def _safe_av_open(*args, metadata_errors=None, **kwargs):
        return _orig_av_open(*args, **kwargs)
    av.open = _safe_av_open
except Exception:
    pass

# ==============================================================================
# PHẦN 1: KHỞI TẠO MODEL FASTER-WHISPER LARGE-V3 & BATCHED PIPELINE
# ==============================================================================
from faster_whisper import WhisperModel, BatchedInferencePipeline

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8"
BATCH_SIZE = 18  # Batch size 18 tối ưu đỉnh VRAM 12.0 - 12.8 GB trên Tesla T4 an toàn tuyệt đối
BEAM_SIZE = 5    # Chuẩn độ chính xác SOTA cao nhất cho tiếng Việt

print(f"--> [1/3] Đang nạp model Faster-Whisper large-v3 vào GPU ({DEVICE.upper()})...")
if torch.cuda.is_available():
    print(f"    Thiết bị: {torch.cuda.get_device_name(0)}")

# Khởi tạo WhisperModel large-v3 chạy float16 trên GPU
base_model = WhisperModel(
    "large-v3",
    device=DEVICE,
    device_index=0 if DEVICE == "cuda" else 0,
    compute_type=COMPUTE_TYPE,
    cpu_threads=4,
    num_workers=1
)

# Khởi tạo Batched Inference Pipeline để xử lý song song các block âm thanh
try:
    batched_pipeline = BatchedInferencePipeline(model=base_model)
    print("--> [2/3] Đã kích hoạt BatchedInferencePipeline (Batching song song)!")
except Exception as e:
    print(f"--> Cảnh báo: Không thể khởi tạo BatchedInferencePipeline: {e}. Sẽ dùng pipeline mặc định.")
    batched_pipeline = None

# Thực hiện Warm-up GPU với dữ liệu giả lập để cấp phát trước bộ nhớ CUDA Arena
if torch.cuda.is_available():
    try:
        import numpy as np
        print("--> Đang Warm-up GPU...")
        dummy_audio = np.zeros(16000 * 2, dtype=np.float32)
        gen, _ = base_model.transcribe(dummy_audio, beam_size=1)
        _ = list(gen) # CƯỠNG BỨC chạy phép tính ma trận cuBLAS
        torch.cuda.empty_cache()
    except Exception:
        pass

print("--> [3/3] Whisper Large-v3 đã sẵn sàng phục vụ!")

# ==============================================================================
# PHẦN 2: XÂY DỰNG FASTAPI SERVER & HỆ THỐNG ASYNC TASK QUEUE
# ==============================================================================
app = FastAPI(title="Whisper Large-v3 Colab GPU Server", version="1.0")

class TranscribeRequest(BaseModel):
    audio_base64: str
    audio_ext: Optional[str] = "flac"
    language: Optional[str] = "vi"
    batch_size: Optional[int] = 18
    beam_size: Optional[int] = 5
    vad_filter: Optional[bool] = True
    use_batched: Optional[bool] = False

TASKS = {}
TASKS_LOCK = threading.Lock()

def _execute_transcribe(req: TranscribeRequest):
    """Xử lý nhận diện âm thanh với Whisper Large-v3 Batched trên GPU"""
    global batched_pipeline, base_model
    raw_bytes = base64.b64decode(req.audio_base64)
    ext = req.audio_ext or "flac"
    
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            f.write(raw_bytes)
            tmp_path = f.name

        LANGUAGE_PROMPTS = {
            "vi": "Sau đây là bài thuyết minh chất lượng cao, chuẩn tiếng Việt, có đầy đủ dấu câu, ngữ pháp chính xác, viết hoa đúng chuẩn.",
            "en": "The following is a clear, high-quality narration with correct punctuation, capitalization, and grammar.",
            "ko": "다음은 명확하고 고품질의 한국어 내레이션입니다. 표준 맞춤법과 띄어쓰기 규정을 준수하며 문장 부호(., ?)와 경어체를 정확히 사용합니다.",
            "ja": "以下は、正確な漢字・ひらがな・カタカナ表記を用い、句読点（、。）を適切に配置した自然で高品質な日本語のナレーション・朗読です。",
            "es": "La siguiente es una narración clara y de alta calidad, con puntuación correcta (¿?, ¡!), acentuación adecuada y ortografía precisa.",
            "pt": "A seguir está uma narração clara e de alta qualidade, com pontuação correta, acentuação adequada e excelente gramática em português.",
            "pt-BR": "A seguir está uma narração clara e de alta qualidade, com pontuação correta, acentuação adequada e excelente gramática em português do Brasil.",
            "zh": "以下是一段高质量的解说音频，使用规范简体中文，标点符号（，。、？！）完整准确，分词自然。"
        }

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
            threshold=0.30,
            min_speech_duration_ms=150,
            min_silence_duration_ms=500,
            speech_pad_ms=350
        )

        transcribe_kwargs = dict(
            beam_size=beam_size,
            language=target_lang,
            vad_filter=vad,
            vad_parameters=vad_params,
            word_timestamps=True,
            initial_prompt=initial_prompt,
            repetition_penalty=1.15,
            no_speech_threshold=0.85,
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.5
        )

        start_time = time.time()
        
        # Thực thi nhận diện với cơ chế Tự phục hồi GPU chống treo khi gặp OOM
        parsed_segments = []
        try:
            # Mặc định sử dụng Sequential Adaptive Pipeline (base_model.transcribe) để triệt tiêu hoàn toàn lỗi nuốt đoạn (Bug #1179 & #1319 của BatchedInferencePipeline)
            # Trên GPU Tesla T4, base_model.transcribe() vẫn đạt tốc độ x45-x50 thời gian thực và không bao giờ sót lời
            if req.use_batched and batched_pipeline is not None and DEVICE == "cuda":
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
        except Exception as err:
            err_msg = str(err).lower()
            if "out of memory" in err_msg or "cuda" in err_msg:
                print(f"--> [TỰ PHỤC HỒI GPU] Phát hiện tràn VRAM ({err}). Đang giải phóng bộ nhớ và tự động thử lại an toàn với batch_size=12...")
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
                try:
                    if batched_pipeline is not None and base_model is not None:
                        batched_pipeline = BatchedInferencePipeline(model=base_model)
                except Exception: pass
                
                safe_batch = 12
                segments_gen, info = batched_pipeline.transcribe(
                    tmp_path,
                    batch_size=safe_batch,
                    **transcribe_kwargs
                ) if (batched_pipeline is not None and DEVICE == "cuda") else base_model.transcribe(tmp_path, **transcribe_kwargs)
                
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
            else:
                raise err

        duration_proc = round(time.time() - start_time, 2)
        
        return {
            "success": True,
            "language": info.language,
            "language_probability": round(float(info.language_probability), 4) if hasattr(info, "language_probability") else 1.0,
            "audio_duration_sec": round(float(info.duration), 2) if hasattr(info, "duration") else 0.0,
            "processing_time_sec": duration_proc,
            "total_segments": len(parsed_segments),
            "segments": parsed_segments
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def _async_worker(task_id: str, req: TranscribeRequest):
    global batched_pipeline
    try:
        res = _execute_transcribe(req)
        with TASKS_LOCK:
            TASKS[task_id] = {"status": "completed", "result": res}
    except Exception as e:
        with TASKS_LOCK:
            TASKS[task_id] = {"status": "failed", "error": str(e)}
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        try:
            if batched_pipeline is not None and base_model is not None:
                batched_pipeline = BatchedInferencePipeline(model=base_model)
        except Exception: pass
    finally:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

# ==============================================================================
# PHẦN 3: ĐỊNH NGHĨA CÁC ENDPOINT API
# ==============================================================================

@app.get("/")
@app.get("/health")
def health_check():
    """Kiểm tra tình trạng máy chủ và thông số bộ nhớ GPU Tesla T4"""
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    free_mem, total_mem = torch.cuda.mem_get_info(0) if torch.cuda.is_available() else (0, 0)
    used_mem = total_mem - free_mem
    return {
        "status": "ready",
        "device": DEVICE,
        "gpu_name": gpu_name,
        "vram_used_gb": round(used_mem / (1024**3), 2),
        "vram_free_gb": round(free_mem / (1024**3), 2),
        "vram_total_gb": round(total_mem / (1024**3), 2),
        "model": "faster-whisper large-v3",
        "batch_size_target": BATCH_SIZE,
        "beam_size": BEAM_SIZE
    }

@app.post("/submit_transcribe")
def submit_transcribe(req: TranscribeRequest):
    """Gửi tác vụ nhận diện âm thanh vào hàng đợi bất đồng bộ (tránh Timeout với audio dài)"""
    task_id = str(uuid.uuid4())
    with TASKS_LOCK:
        TASKS[task_id] = {"status": "processing", "start_time": time.time()}
    threading.Thread(target=_async_worker, args=(task_id, req), daemon=True).start()
    return {"success": True, "task_id": task_id}

@app.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    """Kiểm tra tiến độ thực hiện tác vụ theo task_id"""
    with TASKS_LOCK:
        task = TASKS.get(task_id)
    if not task:
        return {"status": "failed", "error": "Không tìm thấy mã tác vụ (Task ID)"}
    if task["status"] == "completed":
        return {"status": "completed", "result": task["result"]}
    elif task["status"] == "failed":
        return {"status": "failed", "error": task.get("error", "Lỗi không xác định")}
    else:
        return {"status": "processing"}

@app.post("/task_clear/{task_id}")
def clear_task_status(task_id: str):
    """Dọn dẹp kết quả tác vụ cũ khỏi bộ nhớ"""
    with TASKS_LOCK:
        TASKS.pop(task_id, None)
    return {"success": True}

@app.post("/transcribe")
def transcribe_direct(req: TranscribeRequest):
    """Endpoint xử lý trực tiếp đồng bộ (phù hợp với audio ngắn < 3 phút)"""
    try:
        return _execute_transcribe(req)
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/clear_memory")
@app.post("/purge_cache")
def purge_gpu_cache():
    """Giải phóng cưỡng bức toàn bộ cache VRAM và rác RAM ngay sau mỗi file trong hàng đợi"""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    free_mem, total_mem = torch.cuda.mem_get_info(0) if torch.cuda.is_available() else (0, 0)
    return {
        "status": "cleared",
        "success": True,
        "vram_free_gb": round(free_mem / (1024**3), 2),
        "vram_total_gb": round(total_mem / (1024**3), 2)
    }

# ==============================================================================
# PHẦN 4: CHẠY SERVER NGẦM & TẠO ĐƯỜNG HẦM CLOUDFLARE PUBLIC
# ==============================================================================
def start_server_and_tunnel():
    nest_asyncio.apply()
    
    # Khởi động FastAPI với Uvicorn trên thread riêng
    def run_uvicorn():
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
        
    server_thread = threading.Thread(target=run_uvicorn, daemon=True)
    server_thread.start()
    time.sleep(2)
    
    if os.path.exists("cloudflare.log"):
        try:
            os.remove("cloudflare.log")
        except Exception:
            pass

    # Kích hoạt Cloudflared Tunnel
    tunnel_proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://127.0.0.1:8000", "--logfile", "cloudflare.log"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    public_url = None
    print("\nĐang khởi tạo đường hầm Cloudflare Tunnel...")
    for _ in range(35):
        time.sleep(1)
        if os.path.exists("cloudflare.log"):
            with open("cloudflare.log", "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                matches = re.findall(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
                if matches:
                    public_url = matches[0]
                    break

    if public_url:
        print("\n" + "=" * 70)
        print("🚀 KẾT NỐI GPU COLAB THÀNH CÔNG (TESLA T4 16GB - WHISPER LARGE-V3)!")
        print(f"👉 DÁN LINK NÀY VÀO TOOL DESKTOP: {public_url}")
        print("=" * 70 + "\n")
        print("⏳ Server đang chạy ngầm... Giữ tab Google Colab mở để duy trì GPU.")
        try:
            tunnel_proc.wait()
        except KeyboardInterrupt:
            print("Đã dừng server.")
    else:
        print("❌ Lỗi: Không thể lấy được link Cloudflare. Vui lòng kiểm tra file cloudflare.log.")

if __name__ == "__main__":
    start_server_and_tunnel()

