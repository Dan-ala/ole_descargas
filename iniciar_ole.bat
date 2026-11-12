@echo off
cd /d "%~dp0"
echo ========================================================
echo   OBSERVATORIO LABORAL PARA LA EDUCACION (OLE)
echo   Iniciando interfaz grafica de movilidad...
echo ========================================================
py -3.13 main.py
if errorlevel 1 (
    echo.
    echo Probando con comando python generico...
    python main.py
    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo iniciar la aplicacion.
        pause
    )
)
