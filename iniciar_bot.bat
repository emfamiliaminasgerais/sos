@echo off
title Hub da Central de Atendimento MG - Iniciar
cd /d "%~dp0"

echo ===================================================
echo   INICIANDO HUB DA CENTRAL DE ATENDIMENTO MG
echo ===================================================
echo.
echo [1/4] Verificando Docker...
docker info >nul 2>&1
if %ERRORLEVEL% == 0 goto docker_running

echo Iniciando o servico do Docker...
powershell -Command "Start-Process powershell -ArgumentList '-NoProfile -Command Start-Service com.docker.service' -Verb RunAs -Wait"

if exist "C:\Program Files\Docker\Docker\resources\com.docker.backend.exe" (
    start "" "C:\Program Files\Docker\Docker\resources\com.docker.backend.exe"
) else (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
)
echo Aguardando o Docker inicializar...

:wait_docker
ping 127.0.0.1 -n 4 > nul
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Ainda aguardando a inicializacao do Docker...
    goto wait_docker
)
echo Docker iniciado com sucesso!

:docker_running
echo.
echo [2/4] Iniciando containers da Evolution API...
cd evolution-api
docker compose up -d
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Falha ao iniciar os containers do Docker.
    pause
    exit /b
)
cd ..

echo.
echo [3/4] Aguardando API inicializar...
ping 127.0.0.1 -n 6 > nul

echo.
echo [4/4] Iniciando o Hub da Central MG (Python)...
start "Hub Central MG" cmd /k "title Hub Central MG && .\venv\Scripts\python.exe app.py"

echo.
echo ===================================================
echo   SISTEMA INICIADO COM SUCESSO!
echo ===================================================
echo O sistema esta rodando em segundo plano.
echo.
ping 127.0.0.1 -n 4 > nul
