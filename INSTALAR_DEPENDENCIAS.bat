@echo off
chcp 65001 >nul
title Instalador de Dependencias - Painel Produtos Degust
echo.
echo ==================================================
echo   INSTALADOR DE DEPENDENCIAS
echo   Painel Produtos Degust
echo ==================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ERRO: Python nao encontrado!
    pause
    exit /b 1
)

python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

if %errorlevel% neq 0 (
    pip install streamlit==1.31.0 requests==2.31.0 pandas==2.2.0 openpyxl==3.1.2 tzdata
)

echo.
echo ✅ Instalacao concluida!
echo Execute EXECUTAR_PAINEL_PRODUTOS.bat
pause
