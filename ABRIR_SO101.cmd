@echo off
rem Abre el programa unico: rangos, alineacion, preparacion y chatbot.
rem Abrirlo no activa motores. Con argumentos (por ejemplo --help) se ejecuta en esta consola.
setlocal
cd /d "%~dp0"
call "%~dp0ENTORNO_PYTHON.cmd"
if errorlevel 1 exit /b 1
if not exist "salidas\diagnostico" mkdir "salidas\diagnostico"
if "%~1"=="" goto ventana
"%PYTHON_EXE%" -X utf8 -m so101er.programa --raiz "%~dp0." %*
exit /b %errorlevel%
:ventana
start "" "%PYTHONW_EXE%" -X utf8 -m so101er.programa --raiz "%~dp0." 2>"salidas\diagnostico\programa_error.log"
