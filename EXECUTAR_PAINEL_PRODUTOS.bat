@echo off
chcp 65001 >nul
title Painel Produtos Degust
echo ==================================================
echo   PAINEL PRODUTOS DEGUST
echo ==================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ERRO: Python nao encontrado!
    echo Execute INSTALAR_DEPENDENCIAS.bat antes de continuar.
    pause
    exit /b 1
)

python -c "import streamlit" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ERRO: Streamlit nao encontrado!
    echo Execute INSTALAR_DEPENDENCIAS.bat antes de continuar.
    pause
    exit /b 1
)

echo ✅ Verificacoes concluidas!
echo URL: http://localhost:8503
echo Para parar: Ctrl+C
echo ==================================================
echo.

python -m streamlit run app_produtos.py --server.port 8503 --server.headless false
pause
