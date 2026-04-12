@echo off
REM Unity Architect AI — Backend PyInstaller build scripti (Windows)
REM Kullanim: build_backend.bat
REM Once: pip install pyinstaller

setlocal
cd /d "%~dp0"

echo === Backend build basliyor ===

set PYINSTALLER=venv\Scripts\pyinstaller.exe

if not exist "%PYINSTALLER%" (
  echo PyInstaller bulunamadi. Yukleniyor...
  venv\Scripts\pip.exe install pyinstaller
)

REM Eski build'i temizle
if exist dist\backend rmdir /s /q dist\backend
if exist build\backend rmdir /s /q build\backend

echo --- PyInstaller calistiriliyor ---
"%PYINSTALLER%" backend.spec

echo.
echo === Build tamamlandi: dist\backend\ ===
echo Binary: dist\backend\backend.exe
