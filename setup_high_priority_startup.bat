@echo off
echo ===================================================
echo   Installing Jarvis with HIGH PRIORITY Startup
echo ===================================================

set "PYTHONW_PATH=C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\pythonw.exe"
set "JARVIS_PATH=C:\Users\ADMIN\Downloads\jarvis-main\jarvis-main\jarvis.py"
set "STARTUP_VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\start_jarvis_silent.vbs"

:: 1. Remove old slow shortcut from Startup folder
if exist "%STARTUP_VBS%" (
    echo [1/2] Removing old slow Startup folder shortcut...
    del /f /q "%STARTUP_VBS%"
)

:: 2. Register into Windows Registry Run (high priority instant startup on logon)
echo [2/2] Registering to Windows Registry Run (Instant Logon)...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "JarvisAssistant" /t REG_SZ /d "\"%PYTHONW_PATH%\" \"%JARVIS_PATH%\"" /f

echo ===================================================
echo   Setup Complete! Jarvis will now start instantly on Windows logon.
echo ===================================================
