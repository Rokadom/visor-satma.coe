@echo off
setlocal EnableExtensions
title REPARAR GIT - VISOR SATMA

set "REPO=D:\web\visor-satma-GitHub"
set "URL=https://github.com/Rokadom/visor-satma.coe.git"
set "TMP=D:\web\_SATMA_GIT_REPARACION"
set "OLD=%REPO%\.git_DANADO_20260926"

echo ============================================================
echo   REPARACION LIMPIA DE GIT - VISOR SATMA
echo ============================================================
echo.
echo NO modifica los archivos del visor, radar ni tronadas.
echo Solo reconstruye la carpeta .git.
echo.

if not exist "%REPO%\index.html" (
  echo ERROR: No se encontro %REPO%\index.html
  pause
  exit /b 1
)

if exist "%TMP%" rmdir /S /Q "%TMP%"

echo [1/6] Descargando estructura Git limpia desde GitHub...
git clone --no-checkout "%URL%" "%TMP%"
if errorlevel 1 (
  echo.
  echo ERROR: No se pudo conectar/clonar el repositorio de GitHub.
  echo No se modifico nada en %REPO%.
  pause
  exit /b 1
)

echo [2/6] Verificando rama main...
git -C "%TMP%" rev-parse --verify origin/main >nul 2>&1
if errorlevel 1 (
  echo ERROR: GitHub no devolvio origin/main.
  rmdir /S /Q "%TMP%"
  pause
  exit /b 1
)

echo [3/6] Guardando la carpeta .git danada...
cd /d "%REPO%"
if exist ".git_DANADO_20260926" rmdir /S /Q ".git_DANADO_20260926"
if exist ".git" (
  attrib -h -s ".git" >nul 2>&1
  ren ".git" ".git_DANADO_20260926"
  if errorlevel 1 (
    echo ERROR: No se pudo renombrar la carpeta .git danada.
    rmdir /S /Q "%TMP%"
    pause
    exit /b 1
  )
)

echo [4/6] Instalando estructura Git limpia...
xcopy "%TMP%\.git" "%REPO%\.git\" /E /H /K /Y /I >nul
if errorlevel 1 (
  echo ERROR: No se pudo instalar la nueva carpeta .git.
  if exist "%REPO%\.git" rmdir /S /Q "%REPO%\.git"
  if exist "%REPO%\.git_DANADO_20260926" ren "%REPO%\.git_DANADO_20260926" ".git"
  rmdir /S /Q "%TMP%"
  pause
  exit /b 1
)
rmdir /S /Q "%TMP%" >nul 2>&1

echo [5/6] Ajustando main sin reemplazar archivos locales...
cd /d "%REPO%"
git symbolic-ref HEAD refs/heads/main
for /f "delims=" %%H in ('git rev-parse refs/remotes/origin/main') do set "REMOTE=%%H"
git update-ref refs/heads/main %REMOTE%
if errorlevel 1 goto RESTAURAR

git config branch.main.remote origin
git config branch.main.merge refs/heads/main

echo [6/6] Verificando repositorio...
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 goto RESTAURAR

echo.
echo ============================================================
echo GIT REPARADO CORRECTAMENTE
echo ============================================================
echo.
echo Sus archivos actuales NO fueron reemplazados.
echo La copia de seguridad de la carpeta Git danada queda en:
echo %OLD%
echo.
echo Ahora ejecute PUBLICAR_RADAR_RD_GITHUB.cmd
echo.
pause
exit /b 0

:RESTAURAR
echo.
echo ERROR durante la reconstruccion. Restaurando .git anterior...
if exist "%REPO%\.git" rmdir /S /Q "%REPO%\.git"
cd /d "%REPO%"
if exist ".git_DANADO_20260926" ren ".git_DANADO_20260926" ".git"
echo Restauracion terminada. Los archivos del visor no fueron modificados.
pause
exit /b 1
