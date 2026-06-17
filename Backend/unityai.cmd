@echo off
REM unityai CLI wrapper (Windows) — 'unityai' bash scriptinin karsiligi.
REM agy/CLI bunu run_command ile cagirir. Paketlenmis build: backend.exe;
REM dev: venv python.
setlocal
set "SCRIPT_DIR=%~dp0"
set "ORIG_PWD=%CD%"
REM Turkce karakterler icin UTF-8 stdio (cp1252 UnicodeEncodeError fix).
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Backend'in yazdigi env dosyasi (UNITYAI_URL, LOCAL_APP_TOKEN, WORKSPACE).
if exist "%SCRIPT_DIR%.unityai_cli.env" (
  for /f "usebackq eol=# tokens=1* delims==" %%a in ("%SCRIPT_DIR%.unityai_cli.env") do set "%%a=%%b"
)
if not defined WORKSPACE set "WORKSPACE=%ORIG_PWD%"

cd /d "%SCRIPT_DIR%"

REM Paketlenmis build: donmus backend.exe yanindaysa onu calistir.
if exist "%SCRIPT_DIR%backend.exe" (
  "%SCRIPT_DIR%backend.exe" unityai %*
  exit /b %ERRORLEVEL%
)

REM Dev: venv python, yoksa sistem python.
set "PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%SCRIPT_DIR%app;%PYTHONPATH%"
"%PYTHON%" -m app.unityai_cli %*
exit /b %ERRORLEVEL%
