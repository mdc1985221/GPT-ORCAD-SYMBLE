@echo off
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0orcad-assistant\web_app.py"
    exit /b
)
set "SYMBOL_PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%SYMBOL_PYTHON%" (
    "%SYMBOL_PYTHON%" "%~dp0orcad-assistant\web_app.py"
) else (
    py -3 "%~dp0orcad-assistant\web_app.py"
)
