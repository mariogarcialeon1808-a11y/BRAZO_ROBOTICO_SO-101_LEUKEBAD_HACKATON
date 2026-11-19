@echo off
rem Abre la cara del robot en Chrome o en Edge a pantalla completa (modo kiosko).
rem La sirve el programa (ABRIR_SO101.cmd o INICIAR_SIMULACION.cmd): se puede abrir antes o despues.
rem Alt+F4 cierra el navegador. Puerto distinto: set CARA_PUERTO=... (y [cara] puerto en config\so101er.toml).
setlocal
cd /d "%~dp0"
if not defined CARA_PUERTO set "CARA_PUERTO=8765"
set "URL=http://127.0.0.1:%CARA_PUERTO%/"
set "PROFILE=%~dp0.cara-profile"

set "CHROME=%CHROME_PATH%"
if not defined CHROME if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "CHROME=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined CHROME if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "CHROME=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined CHROME (
  echo No se encontro Chrome ni Edge. Define CHROME_PATH con la ruta del navegador.
  pause
  exit /b 1
)

echo Esperando a que el programa sirva la cara en %URL% ...
powershell -NoProfile -Command "for($i=0;$i -lt 180;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 '%URL%salud' | Out-Null; exit 0}catch{Start-Sleep 1}}; exit 1"
if errorlevel 1 echo La cara no responde todavia; se abre igualmente.

start "" "%CHROME%" ^
  --kiosk ^
  --user-data-dir="%PROFILE%" ^
  --no-first-run ^
  --no-default-browser-check ^
  --noerrdialogs ^
  --hide-crash-restore-bubble ^
  --overscroll-history-navigation=0 ^
  --lang=es-ES ^
  --check-for-update-interval=31536000 ^
  "%URL%"
endlocal
