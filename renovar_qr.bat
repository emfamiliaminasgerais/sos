@echo off
title Renovar QR Code WhatsApp
cd /d "%~dp0"
echo ===================================================
echo   RENOVANDO O QR CODE DO WHATSAPP
echo ===================================================
echo.
.\venv\Scripts\python.exe get_qr.py
echo.
echo ===================================================
echo   QR CODE ATUALIZADO!
echo ===================================================
echo Agora atualize a pagina "qr.html" no seu navegador.
echo.
pause
