@echo off
title Parar Bot WhatsApp
cd /d "%~dp0"

echo ===================================================
echo   ENCERRANDO OS SERVICOS DO BOT E LIBERANDO MEMORIA
echo ===================================================
echo.
echo [1/2] Parando o motor do Bot (Python)...
:: Encerra a janela do cmd e o processo do python rodando dentro dela (/t derruba a arvore de processos)
taskkill /f /t /fi "WINDOWTITLE eq WhatsApp Bot Engine" >nul 2>&1
echo Motor Python finalizado.

echo.
echo [2/3] Parando containers do Docker...
cd evolution-api
docker compose down
cd ..

echo.
echo [3/3] Parando a Engine do Docker para liberar RAM (pode pedir permissao de administrador)...
taskkill /f /im com.docker.backend.exe >nul 2>&1
powershell -Command "Start-Process powershell -ArgumentList '-NoProfile -Command Stop-Service com.docker.service' -Verb RunAs -Wait"

echo.
echo ===================================================
echo   TODOS OS SERVICOS FORAM PARADOS E MEMORIA LIBERADA!
echo ===================================================
echo Seu PC agora esta livre para rodar jogos com 100%% de desempenho!
echo.
ping 127.0.0.1 -n 6 > nul
