@echo off
setlocal
cd /d "%~dp0"
set NUITKA_CACHE_DIR=%CD%\build\nuitka-cache

.venv\Scripts\python.exe -m nuitka ^
  --standalone ^
  --disable-cache=all ^
  --assume-yes-for-downloads ^
  --module-parameter=numba-disable-jit=yes ^
  --enable-plugin=pyside6 ^
  --include-package=HEPiC ^
  --include-data-file=HEPiC\config.json=HEPiC\config.json ^
  --output-dir=build ^
  --output-filename=HEPiC.exe ^
  run_hepic.py
