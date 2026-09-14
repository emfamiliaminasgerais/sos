@echo off
title Enviar Projeto para GitHub Pages
cd /d "%~dp0"
echo ===================================================
echo   ENVIANDO HUB DA CENTRAL MG PARA O GITHUB PAGES
echo ===================================================
echo.
echo Abrindo autenticacao do GitHub no navegador...
git push -u origin main
echo.
if %ERRORLEVEL% == 0 (
    echo ===================================================
    echo   SUCESSO! PROJETO ENVIADO PARA O GITHUB!
    echo ===================================================
) else (
    echo [ERRO] Ocorreu uma falha no envio.
)
pause
