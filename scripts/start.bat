@echo off
REM Запуск backend (uvicorn) + frontend (vite) в двух окнах.
setlocal
cd /d "%~dp0\.."

echo === YouTube Auto Studio ===
echo Запуск backend на http://127.0.0.1:8000
REM venv перенесён на локальный диск (вне Google Drive) — pip/torch/kokoro
REM ставятся и работают там быстрее и без блокировок виртуального тома Drive
start "YAS Backend" cmd /k "cd backend && "%USERPROFILE%\Projects\YouTube Auto Studio-backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo Запуск frontend на http://localhost:5173
REM frontend перенесён на локальный диск (вне Google Drive) из-за блокировок npm на синхронизируемом томе
start "YAS Frontend" cmd /k "cd /d "%USERPROFILE%\Projects\YouTube Auto Studio-frontend" && npm run dev"

echo Запуск синхронизации frontend -> Google Диск (бэкап исходников для других компьютеров)
start "YAS Sync" cmd /k "scripts\sync_frontend.bat"

echo Открой http://localhost:5173 в браузере.
endlocal
