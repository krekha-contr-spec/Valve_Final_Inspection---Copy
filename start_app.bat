@echo off
cd /d "%~dp0"
call app\Scripts\activate
set SDK_PATH=c:\Programs Files (x86)\MVS\Development\Bin\win64
set PATH=%SDK_PATH%;%PATH%
set MV_CAM_CTRL_PATH=%SDK_PATH%
echo SDK PATH:
echo %SDK_PATH%
echo.
for /f %%p in ('python -c "import os; print(os.environ.get('PORT', 7000))"') do set PORT=%%p
for /f "tokens=14" %%i in ('ipconfig ^| findstr /i "IPv4"') do set IP=%%i
start "" "http://%IP%:%PORT%"
:loop
python main.py
timeout /t 3 >nul
goto loop
