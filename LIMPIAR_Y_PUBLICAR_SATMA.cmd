@echo off
setlocal EnableExtensions
title SATMA - LIMPIAR Y PUBLICAR
set "REPO=D:\web\visor-satma-GitHub-NUEVO"
echo ============================================================
echo SATMA - PUBLICACION SIN ARCHIVOS PESADOS
echo ============================================================
echo Trabajando SOLO en %REPO%
if not exist "%REPO%\.git" (echo ERROR: Falta el repositorio limpio.&pause&exit /b 1)
cd /d "%REPO%"
echo [1/5] Recuperando main limpio...
git fetch origin main
if errorlevel 1 goto ERROR
git reset --mixed origin/main
if errorlevel 1 goto ERROR
echo [2/5] Excluyendo GRIB pesados...
>>".gitignore" echo.
>>".gitignore" echo # Modelos pesados - no publicar
>>".gitignore" echo *.grib2
>>".gitignore" echo *.grb2
>>".gitignore" echo *.grib
>>".gitignore" echo *.grb
echo [3/5] Preparando cambios...
git add -A
if errorlevel 1 goto ERROR
echo [4/5] Quitando del commit cualquier archivo mayor de 95 MB...
for /f "delims=" %%F in ('git diff --cached --name-only --diff-filter^=ACM') do call :CHECK "%%F"
git add .gitignore
git diff --cached --quiet
if not errorlevel 1 goto OK
git commit -m "Actualizar SATMA Radar RD sin archivos pesados"
if errorlevel 1 goto ERROR
echo [5/5] Publicando...
git push origin main
if errorlevel 1 goto ERROR
:OK
echo.
echo ============================================================
echo PUBLICACION COMPLETADA CORRECTAMENTE
echo ============================================================
echo Carpeta de trabajo: %REPO%
echo La carpeta original no fue modificada.
pause
exit /b 0
:CHECK
set "REL=%~1"
if not exist "%REPO%\%REL%" exit /b 0
for %%Z in ("%REPO%\%REL%") do set "SIZE=%%~zZ"
if %SIZE% GTR 99614720 (
 echo EXCLUIDO POR TAMANO: %REL%
 git reset -q HEAD -- "%REL%"
 >>".gitignore" echo /%REL:\=/%
)
exit /b 0
:ERROR
echo.
echo ERROR: La publicacion no se completo.
echo La carpeta original no fue modificada.
pause
exit /b 1
