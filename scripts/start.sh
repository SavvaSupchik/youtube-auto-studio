#!/usr/bin/env bash
# Запуск backend (uvicorn) + frontend (vite). Останавливается по Ctrl+C.
set -e
cd "$(dirname "$0")/.."

echo "=== YouTube Auto Studio ==="

(cd backend && "$HOME/Projects/YouTube Auto Studio-backend/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) &
BACKEND_PID=$!

(cd "$HOME/Projects/YouTube Auto Studio-frontend" && npm run dev) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
echo "Backend:  http://127.0.0.1:8000  (docs: /docs)"
echo "Frontend: http://localhost:5173"
wait
