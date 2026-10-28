@echo off
title CapCut Audio to Text Tool
cls

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
echo =======================================================================
echo [LOI] Khong tim thay Python tren may tinh cua ban!
echo.
echo Vui long cai dat Python tai: https://www.python.org/downloads/
echo LUU Y: Khi cai dat, nho tich chon vao o: [x] Add python.exe to PATH
echo sau do chay lai file "install.bat" truoc khi mo tool.
echo =======================================================================
echo.
pause
exit /b 1

:found_python
echo Dang khoi chay CapCut Audio to Text Tool...
%PYTHON_CMD% capcut_audio_to_text.py

if %errorlevel% neq 0 (
    echo.
    echo =======================================================================
    echo [LOI] Da xay ra su co khi chay ung dung.
    echo Hay dam bao ban da chay file "install.bat" de cai dat du thu vien truoc do!
    echo =======================================================================
    echo.
    pause
)
