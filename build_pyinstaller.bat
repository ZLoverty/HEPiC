@echo off
setlocal
cd /d "%~dp0"

echo [1/2] Checking PyInstaller installation...
.venv\Scripts\python.exe -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller and hooks...
    .venv\Scripts\pip install pyinstaller pyinstaller-hooks-contrib
)

echo [2/2] Building HEPiC...
.venv\Scripts\python.exe -m PyInstaller ^
  --name HEPiC ^
  --windowed ^
  --icon "assets\hepic.ico" ^
  --onedir ^
  --noconfirm ^
  --workpath build\pyinstaller ^
  --distpath dist ^
  --add-data "HEPiC\config.json;HEPiC" ^
  --add-data "HEPiC\tab_widgets\icons;HEPiC\tab_widgets\icons" ^
  --add-data "HEPiC\database;HEPiC\database" ^
  --hidden-import qasync ^
  --collect-all pyqtgraph ^
  run_hepic.py

echo.
if errorlevel 1 (
    echo BUILD FAILED.
) else (
    echo BUILD SUCCEEDED.
    echo Output: dist\HEPiC\HEPiC.exe
)
pause
