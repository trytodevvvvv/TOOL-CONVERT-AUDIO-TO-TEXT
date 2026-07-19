@echo off
chcp 65001 > nul
title CapCut Audio to Text Tool
echo Đang khởi chạy CapCut Audio to Text Tool...
python capcut_audio_to_text.py
if %errorlevel% neq 0 (
    echo.
    echo [LỖI] Đã xảy ra sự cố khi chạy ứng dụng.
    echo Hãy đảm bảo bạn đã chạy file install.bat trước đó để cài đặt đầy đủ thư viện.
    pause
)
