@echo off
title Cai dat moi truong - CapCut Audio to Text Batch Studio
cls
echo =======================================================================
echo          CAI DAT MOI TRUONG - CAPCUT AUDIO TO TEXT BATCH STUDIO
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
echo [1/2] Kiem tra moi truong Python:
%PYTHON_CMD% --version
echo.

echo [2/2] Kiem tra bo xu ly am thanh sieu toc:
REM Cap 1: Uu tien tuyet doi bo xu ly offline ffmpeg.exe di kem
if exist "ffmpeg.exe" (
    echo [OK] Da co san bo xu ly am thanh chuyen dung ffmpeg.exe (Hoat dong 100%% offline sieu toc)!
    goto :install_success
)

REM Cap 2: Kiem tra thu vien ho tro trong Python (neu da co san tu truoc)
%PYTHON_CMD% -c "import imageio_ffmpeg" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Thu vien xu ly am thanh da co san trong Python!
    goto :install_success
)

REM Cap 3: Cai dat bo tro nhanh qua pip (khong nang cap pip, tai truc tiep goi 49KB)
echo Dang cai dat goi ho tro xu ly am thanh sieu nhe (imageio-ffmpeg ~49KB)...
%PYTHON_CMD% -m pip install imageio-ffmpeg --prefer-binary --no-warn-script-location

:install_success
echo.
echo =======================================================================
echo                       CAI DAT HOAN TAT THANH CONG!
echo.
echo  - Tool hoat dong 100%% tren Google Colab GPU Tesla T4 (Whisper Large-v3)
echo  - May tinh khong can tai model nang hay ton RAM/VRAM!
echo.
echo  Ban co the mo ung dung bang cach nhap dup vao file: run.bat
echo =======================================================================
echo.
pause
