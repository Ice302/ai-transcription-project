#!/usr/bin/env sh
# Start TurboTranscribe on macOS / Linux: backend + frontend dev server. Ctrl+C stops both.
set -e
cd "$(dirname "$0")"

free_port() {
  backend/venv/bin/python - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
for p in range(port, port + 20):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", p))
            print(p)
            break
        except OSError:
            continue
PY
}

# First start, or an update changed the dependency lists: install what is missing first.
if [ ! -x backend/venv/bin/python ] || [ ! -d frontend/node_modules ] ||
   ! cmp -s backend/requirements.txt backend/venv/requirements.installed ||
   ! cmp -s frontend/package-lock.json frontend/node_modules/.turbotranscribe-lock; then
  echo "Installing or updating dependencies first. This takes a few minutes the first time..."
  ./setup.sh --auto
fi
BACKEND_PORT=$(free_port "${BACKEND_PORT:-8000}")
FRONTEND_PORT=$(free_port "${FRONTEND_PORT:-5173}")

(cd backend && exec venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT") &
BACK=$!
(cd frontend && BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" exec npm run dev -- --port "$FRONTEND_PORT" --strictPort) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' INT TERM EXIT

echo "TurboTranscribe: http://localhost:$FRONTEND_PORT  (backend on $BACKEND_PORT) - Ctrl+C to stop"
wait
