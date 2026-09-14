@echo off
title Iniciar Bot WhatsApp
cd /d "%~dp0"

echo ===================================================
echo   INICIANDO OS SERVICOS DO BOT (EVOLUTION API)
echo ===================================================
echo.
echo [1/4] Verificando se o Docker esta rodando...
docker info >nul 2>&1
if %ERRORLEVEL% == 0 goto docker_running

echo Docker nao esta rodando. Iniciando o servico do Docker (pode pedir permissao de administrador)...
powershell -Command "Start-Process powershell -ArgumentList '-NoProfile -Command Start-Service com.docker.service' -Verb RunAs -Wait"

echo Iniciando a Engine do Docker...
if exist "C:\Program Files\Docker\Docker\resources\com.docker.backend.exe" (
    start "" "C:\Program Files\Docker\Docker\resources\com.docker.backend.exe"
) else (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
)
echo Aguardando o Docker inicializar (pode levar ate 30 segundos)...

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
echo [2/4] Iniciando containers do Docker...
cd evolution-api
docker compose up -d
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERRO] Falha ao iniciar os containers do Docker.
    pause
    exit /b
)
cd ..

echo.
echo [3/4] Aguardando 5 segundos para inicializacao da API...
ping 127.0.0.1 -n 6 > nul

echo.
echo [4/4] Iniciando o motor do Bot (Python)...
:: Abre o bot em uma nova janela CMD com titulo fixo para podermos fechar depois via script
start "WhatsApp Bot Engine" cmd /k "title WhatsApp Bot Engine && .\venv\Scripts\python.exe app.py"

echo.
echo ===================================================
echo   BOT INICIADO COM SUCESSO!
echo ===================================================
echo O motor do bot esta rodando na janela "WhatsApp Bot Engine".
echo Você pode minimizar as janelas e usar o WhatsApp!
echo.
ping 127.0.0.1 -n 4 > nul
