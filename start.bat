@echo off
echo Iniciando servidor FastAPI...
echo.
echo Asegurate de haber configurado config.py con tus credenciales de PostgreSQL
echo.
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause

