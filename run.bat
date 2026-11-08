@echo off
REM One-command local run (Windows): double-click run.bat
cd /d "%~dp0backend"
if not exist venv python -m venv venv
call venv\Scripts\activate
pip install -q -r requirements.txt
python seed.py
echo.
echo Open http://127.0.0.1:5001/portal/   (login: admin / admin123)
python app.py
