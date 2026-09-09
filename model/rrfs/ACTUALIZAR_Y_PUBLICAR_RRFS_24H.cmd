@echo off
setlocal
title RRFS HISPANIOLA 24H - DESCARGAR + PUBLICAR ONLINE
cd /d "%~dp0"

set "PY=D:\GFS\App GFS\runtime\python.exe"
set "DESC=%~dp0scripts\rrfs_descargar_multivariable_24h_v8_3_verifica_corrida.py"
set "EXP=%~dp0scripts\exportar_rrfs_web_24h.py"
set "REPO=D:\web\visor-satma-GitHub"

echo ============================================================
echo RRFS HISPANIOLA 24H - ACTUALIZACION ONLINE
echo Carpeta: %CD%
echo ============================================================
echo.

if not exist "%PY%" (
  echo ERROR: No se encontro Python:
  echo %PY%
  pause
  exit /b 1
)

if not exist "%DESC%" (
  echo ERROR: No se encontro el descargador:
  echo %DESC%
  pause
  exit /b 1
)

echo [1/3] DESCARGANDO / ACTUALIZANDO RRFS F003..F024...
"%PY%" "%DESC%"
if errorlevel 1 (
  echo ERROR EN LA DESCARGA RRFS.
  pause
  exit /b 1
)

echo.
echo [2/3] GENERANDO DATOS ESTATICOS PARA GITHUB.IO...
"%PY%" "%EXP%"
if errorlevel 1 (
  echo ERROR AL GENERAR LOS DATOS WEB.
  pause
  exit /b 1
)

echo.
echo [3/3] PUBLICANDO model\rrfs EN GITHUB...
cd /d "%REPO%"
git add -A model\rrfs
git diff --cached --quiet
if not errorlevel 1 (
  echo No hay cambios nuevos para publicar.
  goto FIN
)

git commit -m "Actualizar RRFS Hispaniola 24H"
if errorlevel 1 goto ERRORGIT

git push origin main
if errorlevel 1 goto ERRORGIT

echo.
echo PUBLICACION COMPLETADA.
echo https://rokadom.github.io/visor-satma.coe/model/rrfs/
goto FIN

:ERRORGIT
echo.
echo ERROR DURANTE LA PUBLICACION EN GITHUB.
pause
exit /b 1

:FIN
echo.
echo ============================================================
echo RRFS HISPANIOLA 24H FINALIZADO
echo ============================================================
pause
endlocal
