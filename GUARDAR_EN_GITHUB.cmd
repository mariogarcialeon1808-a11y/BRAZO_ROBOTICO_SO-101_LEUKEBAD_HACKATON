@echo off
rem Guarda todo el proyecto en GitHub con un solo comando: anade los cambios, los confirma y los sube.
rem
rem   GUARDAR_EN_GITHUB.cmd                        mensaje con la fecha y la hora
rem   GUARDAR_EN_GITHUB.cmd "Lo que he cambiado"   mensaje propio
rem   GUARDAR_EN_GITHUB.cmd /prueba                ensena lo que haria, sin confirmar ni subir nada
rem
rem La confirmacion va firmada solo por el usuario de git de este equipo (git config user.name y
rem user.email): no se anade ningun coautor. No se suben calibraciones, imagenes, claves ni
rem salidas: lo decide .gitignore, como siempre.
setlocal EnableExtensions
cd /d "%~dp0"

set "PRUEBA="
set "MENSAJE=%~1"
if /i "%~1"=="/prueba" set "PRUEBA=1"
if /i "%~1"=="/prueba" set "MENSAJE=%~2"

where git >nul 2>nul
if errorlevel 1 goto :sin_git
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 goto :sin_repositorio

set "AUTOR="
set "CORREO="
set "RAMA="
set "DESTINO="
for /f "delims=" %%i in ('git config user.name') do set "AUTOR=%%i"
for /f "delims=" %%i in ('git config user.email') do set "CORREO=%%i"
for /f "delims=" %%i in ('git branch --show-current') do set "RAMA=%%i"
for /f "delims=" %%i in ('git remote get-url origin 2^>nul') do set "DESTINO=%%i"
if not defined AUTOR goto :sin_autor
if not defined CORREO goto :sin_autor
if not defined RAMA goto :sin_rama
if not defined DESTINO goto :sin_destino
if not defined MENSAJE for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'dd-MM-yyyy HH:mm'"') do set "MENSAJE=Guardado del %%i"

set "CAMBIOS=0"
for /f %%i in ('git status --porcelain ^| find /c /v ""') do set "CAMBIOS=%%i"

echo Repositorio: %DESTINO%
echo Rama:        %RAMA%
echo Firma:       %AUTOR%
echo Mensaje:     %MENSAJE%
echo.
if "%CAMBIOS%"=="0" goto :sin_cambios
echo Archivos con cambios: %CAMBIOS%
git status --short
echo.
if defined PRUEBA goto :solo_prueba

git add -A
if errorlevel 1 goto :fallo_confirmar
rem Por si .gitignore dejara pasar algo que no debe subirse nunca.
git diff --cached --name-only | findstr /i /r "\.env$ \.pem$ \.key$" >nul
if not errorlevel 1 goto :hay_claves
git commit -q -m "%MENSAJE%"
if errorlevel 1 goto :fallo_confirmar
goto :subir

:sin_cambios
echo No hay cambios nuevos que confirmar.
if defined PRUEBA goto :solo_prueba

:subir
git push origin %RAMA%
if errorlevel 1 goto :fallo_subir
echo.
git log -1 --format="Ultima confirmacion: %%h  firmada por %%an  -  %%s"
echo Todo esta guardado en GitHub.
goto :fin

:solo_prueba
echo MODO DE PRUEBA: no se ha confirmado ni subido nada.
goto :fin

:sin_git
echo No se encuentra git. Instala Git para Windows y vuelve a intentarlo.
goto :fin_error
:sin_repositorio
echo Esta carpeta no es un repositorio de git.
goto :fin_error
:sin_autor
echo Falta tu nombre o tu correo en git. Ponlos una vez con:
echo   git config --global user.name "Tu nombre"
echo   git config --global user.email "tu correo"
goto :fin_error
:sin_rama
echo No hay ninguna rama activa en este repositorio.
goto :fin_error
:sin_destino
echo Este repositorio no tiene destino en GitHub. Anadelo una vez con:
echo   git remote add origin https://github.com/USUARIO/REPOSITORIO.git
goto :fin_error
:hay_claves
git reset -q
echo NO SE HA GUARDADO NADA: entre los cambios hay un archivo de claves (.env, .pem o .key).
echo Quitalo de la carpeta o anadelo a .gitignore y vuelve a intentarlo.
goto :fin_error
:fallo_confirmar
echo No se ha podido confirmar. Mira el mensaje de git de arriba.
goto :fin_error
:fallo_subir
echo.
echo La confirmacion esta hecha en este equipo, pero NO se ha subido a GitHub.
echo Comprueba la conexion o tus credenciales y vuelve a ejecutar este comando.
goto :fin_error

:fin_error
set "RESULTADO=1"
goto :salir
:fin
set "RESULTADO=0"
:salir
rem Con doble clic la ventana se cerraria sin dejar leer nada: se espera una tecla.
if not defined SO101_SIN_PAUSA echo %cmdcmdline% | findstr /i /c:"%~nx0" >nul && pause
exit /b %RESULTADO%
