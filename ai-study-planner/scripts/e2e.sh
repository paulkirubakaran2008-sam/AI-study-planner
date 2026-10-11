#!/usr/bin/env bash
# Boots the API (production mode, gunicorn) + the built frontend, runs the Playwright suite, then shuts everything down.
# Usage: scripts/e2e.sh   (needs: backend venv with deps, `npm run build` done with VITE_API_URL=http://127.0.0.1:8000)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"; GUNICORN="${GUNICORN:-gunicorn}"
cd "$ROOT/backend"; rm -f e2e.db
ENVIRONMENT=production SECRET_KEY="$($PY -c 'import secrets;print(secrets.token_urlsafe(48))')" DATABASE_URL=sqlite:///./e2e.db CORS_ORIGINS=http://127.0.0.1:4173 \
  $GUNICORN app.main:app -k uvicorn.workers.UvicornWorker -w 1 -b 127.0.0.1:8000 > /tmp/api.log 2>&1 &
API=$!
cd "$ROOT/frontend"; npx vite preview --port 4173 --host 127.0.0.1 > /tmp/web.log 2>&1 &
WEB=$!
trap 'kill $API $WEB 2>/dev/null' EXIT
for i in $(seq 1 30); do curl -sf -m 2 http://127.0.0.1:8000/health >/dev/null && curl -sf -m 2 http://127.0.0.1:4173/ >/dev/null && break; sleep 1; done
cd "$ROOT/backend"; $PY tests/e2e_browser.py
