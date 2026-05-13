#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${SESSION_NAME:-dropvoice}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${APP_ROOT}/backend"
VENV_DIR="${APP_ROOT}/.venv"

if ! command -v screen >/dev/null 2>&1; then
  echo "screen is not installed. Run: bash deploy/setup_server_http.sh <public-ip-or-host>"
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/uvicorn" ]]; then
  echo "Missing uvicorn in ${VENV_DIR}. Run the setup script first."
  exit 1
fi

if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
  echo "Missing ${BACKEND_DIR}/.env"
  exit 1
fi

if screen -list | grep -q "[.]${SESSION_NAME}[[:space:]]"; then
  screen -S "${SESSION_NAME}" -X quit || true
  sleep 1
fi

CMD="cd '${BACKEND_DIR}' && exec '${VENV_DIR}/bin/uvicorn' app.main:app --host '${API_HOST}' --port '${API_PORT}'"
screen -dmS "${SESSION_NAME}" bash -lc "${CMD}"

cat <<EOF
Backend started in screen session: ${SESSION_NAME}

Attach:
  screen -r ${SESSION_NAME}

Detach from screen:
  Ctrl+A then D

List sessions:
  screen -ls
EOF
