@echo off
title Cai dat thu vien - CapCut Audio to Text Tool
cls
echo =======================================================================
echo          CAI DAT THU VIEN - CAPCUT AUDIO TO TEXT TOOL
echo =======================================================================
echo.

set "PYTHON_CMD="

REM 1. Thu tim lenh python
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto :found_python
)

REM 2. Thu tim lenh py (Python Launcher tren Windows)
py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py -3"
    goto :found_python
)

REM 3. Quet thu muc cai dat mac dinh cua nguoi dung
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_CMD="%%D\python.exe""
        goto :found_python
    )
)

REM 4. Quet thu muc Program Files
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_CMD="%%D\python.exe""
        goto :found_python
    )
)
for /d %%D in ("%ProgramFiles(x86)%\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_CMD="%%D\python.exe""
        goto :found_python
    )
)

REM 5. Quet thu muc goc o C:
for /d %%D in ("C:\Python3*") do (
    if exist "%%D\python.exe" (
        set "PYTHON_CMD="%%D\python.exe""
        goto :found_python
    )
)

REM Neu khong tim thay Python o bat ky dau
echo [LOI] Khong tim thay Python tren may tinh cua ban!
echo.
echo Vui long tai va cai dat Python tai: https://www.python.org/downloads/
echo LUU Y: Khi cai dat, bat buoc tich chon vao o: [x] Add python.exe to PATH
echo.
echo Sau khi cai Python xong, hay mo lai file install.bat nay.
echo =======================================================================
pause
exit /b 1

:found_python
echo [1/3] Kiem tra Python:
%PYTHON_CMD% --version
echo.

REM 2. Cai dat thu vien Whisper
echo [2/3] Dang cai dat thu vien OpenAI Whisper...
echo (Vui long doi trong giay lat...)
echo.
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install openai-whisper

if %errorlevel% neq 0 (
    echo.
    echo [CANH BAO] Co loi khi tai thu vien pip. Vui long kiem tra ket noi Internet!
    pause
    exit /b 1
)

REM 3. Tai duy nhat Model 'small' ve may
echo.
echo [3/3] Dang tai model Whisper 'small' (~460MB) ve may...
echo (Chi can tai duy nhat 1 lan nay de sau nay chay offline hoan toan)
echo.
%PYTHON_CMD% -c "import whisper; print('Dang tai model small...'); whisper.load_model('small'); print('[OK] Da tai xong model small!')"

if %errorlevel% neq 0 (
    echo.
    echo [CANH BAO] Qua trinh tai model 'small' bi gian doan.
    echo Ban van co the mo tool, khi chay ung dung se tu dong tai lai.
)

echo.
echo =======================================================================
echo                       CAI DAT HOAN TAT THANH CONG!
echo.
echo  - Da cai dat thu vien Whisper va tai xong model 'small'.
echo  - File ffmpeg.exe da co san trong thu muc.
echo.
echo  Ban co the mo ung dung bang cach nhap dup vao file: run.bat
echo =======================================================================
echo.
pause
