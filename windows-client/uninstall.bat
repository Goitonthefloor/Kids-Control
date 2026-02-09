@echo off
REM Kids-Control Windows Client - Uninstallation Script
REM Run as Administrator

echo ========================================
echo Kids-Control Windows Client Uninstaller
echo ========================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running as Administrator
) else (
    echo [WARNING] Running without Administrator privileges
    echo Some cleanup steps may fail
)

echo.
set /p CONFIRM="Are you sure you want to uninstall Kids-Control Client? (Y/N): "
if /i not "%CONFIRM%" == "Y" (
    echo Uninstallation cancelled.
    pause
    exit /b 0
)

REM Stop running client
echo.
echo Stopping running client processes...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Kids-Control*" >nul 2>&1
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq Kids-Control*" >nul 2>&1
echo [OK] Client processes stopped

REM Remove autostart entry
echo.
echo Removing auto-start configuration...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "KidsControlClient" /f >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Auto-start removed
) else (
    echo [INFO] No auto-start entry found
)

REM Ask about config files
echo.
set /p DELETE_CONFIG="Delete configuration and log files? (Y/N): "
if /i "%DELETE_CONFIG%" == "Y" (
    if exist "%USERPROFILE%\.kidscontrol" (
        rmdir /S /Q "%USERPROFILE%\.kidscontrol"
        echo [OK] Configuration files deleted
    ) else (
        echo [INFO] No configuration directory found
    )
) else (
    echo [INFO] Configuration files kept at: %USERPROFILE%\.kidscontrol
)

REM Information about program files
echo.
echo ========================================
echo Uninstallation Complete
echo ========================================
echo.
echo Program files remain at: %CD%
echo You can manually delete this folder if desired.
echo.
echo To completely remove Python dependencies:
echo pip uninstall requests psutil pystray Pillow pywin32
echo.
echo Press any key to exit.
pause >nul
