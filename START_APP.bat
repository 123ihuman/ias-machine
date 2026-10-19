@echo off
title IAS Machine
cd /d "C:\Users\divy0\ias_machine"

REM Install anything missing (fast if already there)
python -m pip install -q python-dotenv requests feedparser beautifulsoup4 lxml pillow pypdfium2 pytesseract openai fpdf2 boto2 boto3 google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib Flask Flask-SQLAlchemy flask-login psycopg2-binary

REM Open Chrome after 4 sec
start "" /B cmd /c "timeout /t 4 /nobreak >nul && start chrome http://127.0.0.1:5000"

echo.
echo IAS Machine starting...
echo Local:  http://127.0.0.1:5000
echo Stop:   Ctrl+C
echo.

python app.py
pause