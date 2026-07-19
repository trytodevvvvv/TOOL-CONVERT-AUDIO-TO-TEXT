@echo off
chcp 65001 > nul
title Cài đặt thư viện - CapCut Audio to Text Tool
echo ========================================================
echo ĐANG TIẾN HÀNH CÀI ĐẶT CÁC THƯ VIỆN CẦN THIẾT...
echo ========================================================
echo.
python -m pip install --upgrade pip
echo Đang cài đặt thư viện OpenAI Whisper và PyTorch...
pip install openai-whisper
echo.
echo Cài đặt hoàn tất! Bạn có thể khởi chạy ứng dụng bằng file run.bat.
echo.
pause
