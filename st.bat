@echo off
call .\.venv\Scripts\Activate.bat
timeout /t 2 /nobreak > nul
.\.venv\Scripts\python.exe webui.py --ip 127.0.0.1 --port 7788
