@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ENTORNO_PYTHON.cmd"
if errorlevel 1 exit /b 1
"%PYTHON_EXE%" -X utf8 -m so101er.cli iniciar --raiz "%~dp0." --demo
if errorlevel 1 pause
