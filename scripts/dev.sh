#!/bin/bash
# One command instead of two terminals. A browser tab cannot start this for
# you — no web page's JavaScript can spawn a local process, that's a hard
# browser security boundary, not a missing feature — but nothing says you
# have to type both halves by hand every time either.
#
#   ./scripts/dev.sh   (or: npm run start)
#
# Runs preflight, starts server.py in the background, starts `npm run dev`
# in the foreground, and stops server.py automatically when you Ctrl+C —
# so this session doesn't leave an orphaned backend running the way several
# manual `python3 server.py &` calls did over the course of building this.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

API_PORT="$(grep -E '^API_PORT=' .env 2>/dev/null | cut -d= -f2)"
API_PORT="${API_PORT:-8081}"

echo "==> preflight"
python3 scripts/preflight.py || {
  echo "==> preflight failed — fix the config above before starting" >&2
  exit 1
}

if lsof -i ":$API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> something is already listening on :$API_PORT — assuming it's server.py, not starting a second one"
  SERVER_PID=""
else
  echo "==> starting server.py on :$API_PORT"
  python3 server.py &
  SERVER_PID=$!

  # Cheap, immediate correctness check — catches "port already in use
  # (missed above)" or an import error dying on startup, so that shows up
  # now instead of as a silent "no backend" banner a minute later.
  sleep 1
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "==> server.py exited immediately — check the error above" >&2
    exit 1
  fi
fi

# Stop both processes when this script exits for any reason (Ctrl+C, error,
# or the frontend exiting on its own) — server.py only if THIS script started
# it. Runs vite directly rather than through `npm run dev`: npm is known to
# not reliably forward SIGINT/SIGTERM through its own child process — verified
# live here, killing the `npm run start` wrapper left both server.py and vite
# still running. Calling the vite binary directly means this script holds its
# real PID and can kill it itself instead of hoping a signal propagates
# through a layer of npm indirection.
FRONTEND_PID=""
cleanup() {
  if [ -n "$FRONTEND_PID" ]; then
    kill "$FRONTEND_PID" 2>/dev/null
  fi
  if [ -n "$SERVER_PID" ]; then
    echo "==> stopping server.py (pid $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null
  fi
}
trap cleanup EXIT INT TERM

echo "==> starting the frontend"
"$REPO_ROOT/node_modules/.bin/vite" &
FRONTEND_PID=$!
wait "$FRONTEND_PID"
