@echo off
rem Instala todas las dependencias del proyecto en .venv (Python 3.11-3.13).
rem No activa motores. El registro completo queda en salidas\diagnostico\instalacion.log
setlocal
cd /d "%~dp0"
if not exist "salidas\diagnostico" mkdir "salidas\diagnostico"
set "LOG=%~dp0salidas\diagnostico\instalacion.log"
echo INICIO %date% %time% > "%LOG%"
set "PY="
for %%V in (3.12 3.13 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; assert (3,11)<=sys.version_info[:2]<=(3,13)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo ERROR: no encuentro Python 3.11, 3.12 o 3.13 >> "%LOG%"
  echo No encuentro Python 3.11-3.13. Instala Python 3.12 desde python.org y vuelve a abrir este archivo.
  pause
  exit /b 1
)
echo Usando %PY% >> "%LOG%"
echo [1/5] Creando entorno .venv con %PY% ...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv >> "%LOG%" 2>&1
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo ERROR: no se pudo crear .venv >> "%LOG%"
  echo No se pudo crear el entorno .venv. Mira %LOG%
  pause
  exit /b 1
)
echo [2/5] Actualizando pip ...
"%VPY%" -m pip install --upgrade pip setuptools wheel >> "%LOG%" 2>&1
echo [3/5] Instalando dependencias del proyecto (puede tardar varios minutos) ...
"%VPY%" -m pip install -e ".[integrado,conversacion,dev]" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR pip install >> "%LOG%"
  echo Fallo la instalacion. Mira %LOG%
  pause
  exit /b 1
)
echo [4/5] Descargando el modelo Whisper base para el microfono ...
"%VPY%" tools\instalar_microfono.py >> "%LOG%" 2>&1
if errorlevel 1 echo AVISO: no se pudo descargar Whisper >> "%LOG%"
echo [5/5] Comprobando que todo importa ...
"%VPY%" -c "import serial, numpy, mujoco, tkinter, cv2, sounddevice, av, faster_whisper, prompt_toolkit, google.genai, anthropic, websockets, pynput, pytest; print('OK: todas las dependencias importan')" >> "%LOG%" 2>&1
if errorlevel 1 (echo ERROR imports >> "%LOG%") else (echo Todo instalado correctamente.)
echo FIN %date% %time% >> "%LOG%"
pause
