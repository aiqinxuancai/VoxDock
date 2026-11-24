@echo off
rem Build the portable Windows package locally (same steps as GitHub Actions).
rem Usage: packaging\windows\build.bat [version]
setlocal
cd /d "%~dp0..\.."

set "VERSION=%~1"
if "%VERSION%"=="" set "VERSION=local"
set "VOXDOCK_VERSION=%VERSION%"

python -m pip install -r requirements.txt pyinstaller || goto :error
pyinstaller packaging\windows\voxdock.spec --noconfirm --clean || goto :error
python packaging\windows\package.py %VERSION% || goto :error

echo.
echo Done: dist\VoxDock\VoxDock.exe
exit /b 0

:error
echo Build failed.
exit /b 1
