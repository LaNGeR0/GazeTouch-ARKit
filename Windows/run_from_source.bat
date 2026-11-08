@echo off
setlocal
cd /d "%~dp0"
py -3.13 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.13 was not found. Install Python 3.13 x64 and retry.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.13 -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
pause
