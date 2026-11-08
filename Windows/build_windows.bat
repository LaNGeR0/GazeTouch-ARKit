@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run_from_source.bat once first.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --onedir --name GazeTouch main.py
echo Build folder: dist\GazeTouch
pause
