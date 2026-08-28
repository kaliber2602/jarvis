@echo off
echo Stopping Jarvis background process...
taskkill /F /IM pythonw.exe 2>nul
if %errorlevel% equ 0 (
    echo Jarvis has been stopped successfully.
) else (
    echo Jarvis was not running.
)
pause
