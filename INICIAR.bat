@echo off
echo.
echo  ========================================
echo    TAXI APP - Instalando dependencias...
echo  ========================================
echo.
python -m pip install -r requirements.txt
echo.
echo  ========================================
echo    Iniciando servidor...
echo  ========================================
echo.
python server.py
pause
