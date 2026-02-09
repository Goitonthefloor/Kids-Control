@echo off
REM Kids-Control Windows Client - Installation Script
REM Run as Administrator

echo ========================================
echo Kids-Control Windows Client Installer
echo ========================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running as Administrator
) else (
    echo [ERROR] This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

REM Check Python installation
echo.
echo Checking Python installation...
python --version >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Python is installed
    python --version
) else (
    echo [ERROR] Python is not installed!
    echo Please install Python from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

REM Install dependencies
echo.
echo Installing dependencies...
pip install -r requirements.txt
if %errorLevel% == 0 (
    echo [OK] Dependencies installed
) else (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

REM Create config directory
echo.
echo Creating configuration directory...
if not exist "%USERPROFILE%\.kidscontrol" (
    mkdir "%USERPROFILE%\.kidscontrol"
    echo [OK] Configuration directory created
) else (
    echo [OK] Configuration directory already exists
)

REM Get configuration from user
echo.
echo ========================================
echo Configuration
echo ========================================
echo.

set /p SERVER_URL="Enter Kids-Control server URL (e.g. http://192.168.1.100:8000): "
set /p USERNAME="Enter child username: "

REM Create config file
echo.
echo Creating configuration file...
(
    echo {
    echo   "server_url": "%SERVER_URL%",
    echo   "username": "%USERNAME%",
    echo   "check_interval": 60,
    echo   "auto_start": true
    echo }
) > "%USERPROFILE%\.kidscontrol\config.json"

if exist "%USERPROFILE%\.kidscontrol\config.json" (
    echo [OK] Configuration file created
    echo Location: %USERPROFILE%\.kidscontrol\config.json
) else (
    echo [ERROR] Failed to create configuration file
    pause
    exit /b 1
)

REM Test server connection
echo.
echo Testing server connection...
python -c "import requests; r = requests.get('%SERVER_URL%/api/check/%USERNAME%', timeout=5); print('[OK] Server is reachable') if r.status_code == 200 else print('[WARNING] Server returned status', r.status_code)"
if %errorLevel% neq 0 (
    echo [WARNING] Could not connect to server
    echo Please check:
    echo - Server URL is correct
    echo - Server is running
    echo - Firewall allows connection
)

REM Setup autostart
echo.
echo Setting up auto-start...
set SCRIPT_PATH=%CD%\KidsControlClient.py
set PYTHON_PATH=%~dp0

REM Use pythonw.exe to run without console window
for /f "delims=" %%i in ('where pythonw') do set PYTHONW_PATH=%%i

if "%PYTHONW_PATH%" == "" (
    echo [WARNING] pythonw.exe not found, using python.exe
    for /f "delims=" %%i in ('where python') do set PYTHONW_PATH=%%i
)

REM Add to registry
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "KidsControlClient" /t REG_SZ /d "\"%PYTHONW_PATH%\" \"%SCRIPT_PATH%\"" /f >nul 2>&1

if %errorLevel% == 0 (
    echo [OK] Auto-start configured
) else (
    echo [WARNING] Could not configure auto-start
)

REM Offer to start client now
echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Configuration:
echo - Server: %SERVER_URL%
echo - Username: %USERNAME%
echo - Config: %USERPROFILE%\.kidscontrol\config.json
echo - Log: %USERPROFILE%\.kidscontrol\client.log
echo.
echo The client will start automatically on login.
echo.

set /p START_NOW="Start client now? (Y/N): "
if /i "%START_NOW%" == "Y" (
    echo.
    echo Starting Kids-Control Client...
    start "Kids-Control Client" pythonw "%SCRIPT_PATH%"
    echo.
    echo [OK] Client started in background
    echo Look for the system tray icon (blue "KC")
)

echo.
echo Installation finished. Press any key to exit.
pause >nul
