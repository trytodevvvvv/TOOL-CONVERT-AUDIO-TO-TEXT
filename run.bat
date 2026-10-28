@echo off
title CapCut Audio to Text Batch Studio
echo Dang khoi chay CapCut Audio to Text Batch Studio...
python capcut_audio_to_text.py
if %errorlevel% neq 0 (
    echo.
    echo [LOI] Da xay ra su co khi chay ung dung.
    pause
)
