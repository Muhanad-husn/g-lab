#!/usr/bin/env bash
# hotpatch.sh — push local code changes into running containers without rebuild.
#
# Usage:  ./hotpatch.sh           # patch both backend + frontend
#         ./hotpatch.sh backend   # backend only (restart uvicorn)
#         ./hotpatch.sh frontend  # frontend only (rebuild & copy dist)
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose"
FE_SERVICE="frontend"
BE_SERVICE="backend"

patch_backend() {
  echo "⟳ Backend: restarting container (volume-mounted, picks up file changes)..."
  $COMPOSE restart "$BE_SERVICE"
  echo "✓ Backend patched."
}

patch_frontend() {
  echo "⟳ Frontend: building local dist..."
  (cd frontend && npm run build)

  CONTAINER=$($COMPOSE ps -q "$FE_SERVICE")
  if [ -z "$CONTAINER" ]; then
    echo "✗ Frontend container not running." >&2
    exit 1
  fi

  echo "⟳ Frontend: copying dist into container..."
  docker cp frontend/dist/. "$CONTAINER":/usr/share/nginx/html/
  echo "✓ Frontend patched (nginx serves new files immediately)."
}

TARGET="${1:-all}"
case "$TARGET" in
  backend)  patch_backend ;;
  frontend) patch_frontend ;;
  all)      patch_backend; patch_frontend ;;
  *)        echo "Usage: $0 [backend|frontend|all]" >&2; exit 1 ;;
esac
