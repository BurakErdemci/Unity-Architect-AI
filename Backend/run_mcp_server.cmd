@echo off
REM Unity Architect AI — MCP Server launcher (Windows)
REM run_mcp_server.sh'in Windows karsiligi. Paketlenmis build: yanindaki
REM backend.exe'yi kullanir (venv/python gerekmez); dev: venv python'a duser.
setlocal
set "SCRIPT_DIR=%~dp0"
set "LOG_FILE=%SCRIPT_DIR%mcp_server.log"
REM Turkce karakterler icin UTF-8 stdio (cp1252 UnicodeEncodeError fix).
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Paketlenmis build: donmus backend.exe yanindaysa onu calistir.
if exist "%SCRIPT_DIR%backend.exe" (
  "%SCRIPT_DIR%backend.exe" mcp-server %* 2>> "%LOG_FILE%"
  exit /b %ERRORLEVEL%
)

REM Dev: venv python, yoksa sistem python.
cd /d "%SCRIPT_DIR%"
set "PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PYTHONPATH=%SCRIPT_DIR%app;%PYTHONPATH%"
"%PYTHON%" -m app.unity_ai_mcp.server %* 2>> "%LOG_FILE%"
exit /b %ERRORLEVEL%
