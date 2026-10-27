@echo off
setlocal enabledelayedexpansion
title Kyoka Discord Bot Launcher

echo ======================================================
echo           KYOKA DISCORD BOT - LOCAL LAUNCHER          
echo ======================================================

set "PY_BIN="

REM 1. Check virtualenv
if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
    goto :FoundPython
)

REM 2. Check standard user installation
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PY_BIN=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe"
    goto :FoundPython
)

REM 3. Check hardcoded path for durga
if exist "C:\Users\durga\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PY_BIN=C:\Users\durga\AppData\Local\Programs\Python\Python311\python.exe"
    goto :FoundPython
)

REM 4. Check py launcher
py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_BIN=py -3"
    goto :FoundPython
)

REM 5. Check PATH python
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_BIN=python"
    goto :FoundPython
)

echo [ERROR] Python 3.11 could not be detected automatically!
echo Please ensure Python 3.11 is installed.
pause
exit /b 1

:FoundPython
echo [OK] Using Python: !PY_BIN!
echo Starting Kyoka Discord Bot...
echo.
!PY_BIN! src\main.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [NOTICE] Bot stopped with exit code %ERRORLEVEL%.
    pause
)
