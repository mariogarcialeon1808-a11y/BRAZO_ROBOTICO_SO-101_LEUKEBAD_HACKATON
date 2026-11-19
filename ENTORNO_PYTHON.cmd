@echo off
rem Busca el Python del proyecto y deja PYTHON_EXE, PYTHONW_EXE y PYTHONPATH preparados.
rem Lo llaman los demas .cmd; por si solo no abre nada ni activa motores.
set "PYTHONPATH=%~dp0src"
set "PYTHONIOENCODING=utf-8"
set "RUNTIME=%LOCALAPPDATA%\so101er-runtime\Scripts"
rem El entorno creado desde Codex queda dentro de la carpeta de datos de esa aplicacion.
if not exist "%RUNTIME%\python.exe" for /d %%D in ("%LOCALAPPDATA%\Packages\OpenAI.Codex_*") do if exist "%%D\LocalCache\Local\so101er-runtime\Scripts\python.exe" set "RUNTIME=%%D\LocalCache\Local\so101er-runtime\Scripts"
if not exist "%RUNTIME%\python.exe" set "RUNTIME=%~dp0.venv\Scripts"
set "PYTHON_EXE=%RUNTIME%\python.exe"
set "PYTHONW_EXE=%RUNTIME%\pythonw.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=pythonw"
"%PYTHON_EXE%" -c "import serial, numpy, mujoco, tkinter" 2>nul
if not errorlevel 1 exit /b 0
echo.
echo No encuentro un Python con las dependencias del proyecto (pyserial, numpy, mujoco).
echo Probado: %PYTHON_EXE%
echo Crea el entorno con:  python -m venv .venv   y   .venv\Scripts\pip install -e ".[integrado]"
echo.
pause
exit /b 1
