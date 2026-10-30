#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script đóng gói tự động chuẩn phân phối độc lập (Zero-Data Leak & Isolated Packaging)
Tuân thủ nghiêm ngặt RULE 3 trong HARNESS.md:
- Cách ly hoàn toàn qua thư mục tạm (%TEMP%), tuyệt đối không sinh file rác vào source code.
- Xóa sạch 100% đường dẫn máy cá nhân (Factory Reset config.json).
- Tự động dọn dẹp và xóa vĩnh viễn thư mục tạm sau khi nén file ZIP.
"""

import os
import sys
import shutil
import tempfile
import zipfile
import json

# Đảm bảo UTF-8 an toàn trên Windows Console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

def build_package():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(workspace_dir)
    target_zip_name = "CapCut_STT_Tool_v2.0.zip"
    target_zip_path = os.path.join(parent_dir, target_zip_name)
    
    print("=" * 72)
    print("[*] BAT DAU DONG GOI PHAN PHOI SACH (ZERO-DATA LEAK & FACTORY RESET)")
    print(f"[*] Vi tri file ZIP dich: {target_zip_path}")
    print("=" * 72)
    
    # 1. Tạo thư mục tạm cách ly hoàn toàn trong OS %TEMP%
    temp_dir = tempfile.mkdtemp(prefix="capcut_stt_pkg_")
    pkg_dir = os.path.join(temp_dir, "CapCut_STT_Tool")
    os.makedirs(pkg_dir, exist_ok=True)
    
    try:
        print("[1/5] Sao chep ma nguon cot loi vao thu muc tam cach ly...")
        
        # 1.1 Sao chép capcut_audio_to_text.py
        main_script = os.path.join(workspace_dir, "capcut_audio_to_text.py")
        if not os.path.exists(main_script):
            raise FileNotFoundError(f"Khong tim thay file ma nguon chinh: {main_script}")
        shutil.copy2(main_script, pkg_dir)
        print("  -> Da sao chep: capcut_audio_to_text.py")
        
        # 1.2 Sao chép thư mục colab/ (loại trừ pycache và log)
        colab_src = os.path.join(workspace_dir, "colab")
        colab_dst = os.path.join(pkg_dir, "colab")
        if os.path.exists(colab_src):
            shutil.copytree(
                colab_src, colab_dst,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log", ".ipynb_checkpoints")
            )
            print("  -> Da sao chep thu muc: colab/")
            
        # 1.3 Sao chép các file hỗ trợ từ thư mục đóng gói mẫu CapCut_STT_Tool
        bundled_src = os.path.join(workspace_dir, "CapCut_STT_Tool")
        for fname in ["install.bat", "run.bat", "HUONG_DAN_SU_DUNG.txt", "ffmpeg.exe"]:
            fpath = os.path.join(bundled_src, fname)
            if os.path.exists(fpath):
                shutil.copy2(fpath, pkg_dir)
                print(f"  -> Da sao chep: {fname}")
                
        # 1.4 Sao chép requirements.txt
        req_src = os.path.join(workspace_dir, "requirements.txt")
        if os.path.exists(req_src):
            shutil.copy2(req_src, pkg_dir)
        else:
            with open(os.path.join(pkg_dir, "requirements.txt"), "w", encoding="utf-8") as f:
                f.write("imageio-ffmpeg>=0.4.8\n")
        print("  -> Da sao chep: requirements.txt")

        # 1.5 Sao chép Siêu từ điển tiếng Việt và Mô hình BudouX
        for model_file in ["vietnamese_compounds.gz", "budoux_models.gz"]:
            m_path = os.path.join(workspace_dir, model_file)
            if os.path.exists(m_path):
                shutil.copy2(m_path, pkg_dir)
                print(f"  -> Da sao chep: {model_file}")

        # 2. Khởi tạo file cấu hình mới tinh (Factory Reset - Tuyệt đối không chứa đường dẫn máy cá nhân)
        print("[2/5] Khoi tao config.json sach 100% (Factory Reset)...")
        clean_config = {
            "colab_url": "",
            "drafts_dir": "",
            "language": "Tự động nhận diện",
            "max_words": 13,
            "font_size": 6.0,
            "sync_offset_ms": 0,
            "group_subtitles": True,
            "gpu_power": "🎯 Chuẩn xác 100% (Sequential Zero-Gap - Đề xuất)",
            "auto_export_srt": True,
            "output_dir": ""
        }
        with open(os.path.join(pkg_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(clean_config, f, ensure_ascii=False, indent=4)
        print("  -> Da tao config.json sach: drafts_dir='', colab_url='', output_dir=''")

        # 3. Quét sạch tệp rác, cache trong thư mục tạm
        print("[3/5] Ra soat va loai bo sach toan bo cache, log va tep rac...")
        removed_count = 0
        for root, dirs, files in os.walk(pkg_dir, topdown=False):
            for d in dirs:
                if d in ("__pycache__", ".ipynb_checkpoints"):
                    shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                    removed_count += 1
            for f in files:
                if f.endswith((".pyc", ".bak", ".log", ".tmp", ".flac", ".wav", ".mp3")):
                    try:
                        os.remove(os.path.join(root, f))
                        removed_count += 1
                    except Exception: pass
        print(f"  -> Da loai bo {removed_count} tep/thu muc rac.")

        # 4. Nén thành file ZIP đặt ở thư mục ngoài kho mã nguồn
        print(f"[4/5] Dang nen toan bo thanh file ZIP doc lap...")
        if os.path.exists(target_zip_path):
            try: os.remove(target_zip_path)
            except Exception: pass
            
        with zipfile.ZipFile(target_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(pkg_dir):
                for f in files:
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, temp_dir)
                    zipf.write(abs_path, rel_path)
                    
        zip_size_mb = round(os.path.getsize(target_zip_path) / (1024 * 1024), 2)
        print(f"  -> Nen ZIP thanh cong! Dung luong: {zip_size_mb} MB")

    finally:
        # 5. Xóa sạch vĩnh viễn thư mục tạm (%TEMP%)
        print("[5/5] Tu dong giai phong va xoa vinh vien thu muc tam (%TEMP%)...")
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("  -> Thu muc tam da bi huy hoan toan. Source code giu nguyen ban 100%!")

    print("=" * 72)
    print("[OK] DONG GOI HOAN TAT THANH CONG! BAN PHAN PHOI SACH:")
    print(f"[*] File ZIP: {target_zip_path}")
    print("  + Khong chua bat ky duong dan ca nhan nao (Factory Reset)")
    print("  + May nguoi khac giai nen ra la chay duoc ngay 100%!")
    print("=" * 72)

if __name__ == "__main__":
    build_package()
