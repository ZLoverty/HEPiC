@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Step 1: PyInstaller packaging
echo ============================================
call build_pyinstaller.bat
if errorlevel 1 (
    echo PyInstaller build failed, aborting.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Step 2: Creating installer with Inno Setup
echo ============================================

set ISCC=""
for %%p in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) do (
    if exist %%p set ISCC=%%p
)

if %ISCC%=="" (
    echo ERROR: Inno Setup not found.
    echo Please install it from: https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)

if not exist installer_output mkdir installer_output

for /f "delims=" %%v in ('.venv\Scripts\python.exe -c "from HEPiC import __version__; print(__version__)"') do set APP_VERSION=%%v
echo Version: %APP_VERSION%
%ISCC% /DAppVersion=%APP_VERSION% installer.iss
if errorlevel 1 (
    echo Inno Setup build failed.
    pause
    exit /b 1
)

pause
