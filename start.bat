@echo off
echo Starting Document Generator Backend...
echo.

cd /d "%~dp0"

:: Activate virtual environment if exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

:: Run FastAPI
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
