#!/usr/bin/env bash
set -euo pipefail

PUBLIC_HOST="${1:-${PUBLIC_HOST:-}}"
API_PORT="${API_PORT:-8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${APP_ROOT}/backend"
VENV_DIR="${APP_ROOT}/.venv"
SITE_NAME="dropvoice"
NGINX_SITE="/etc/nginx/sites-available/${SITE_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
CERTBOT_WEBROOT="/var/www/certbot"

if [[ -z "${PUBLIC_HOST}" ]]; then
  echo "Usage: bash deploy/setup_server_http.sh <public-ip-or-host>"
  exit 1
fi

if [[ ! -f "${BACKEND_DIR}/requirements.txt" ]]; then
  echo "Missing backend requirements at ${BACKEND_DIR}/requirements.txt"
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This script currently supports Debian/Ubuntu servers with apt-get."
  exit 1
fi

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip nginx screen curl

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt"

if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
  cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
fi

sudo mkdir -p "${CERTBOT_WEBROOT}"
sudo chown -R "${USER}":"${USER}" "${CERTBOT_WEBROOT}"

TMP_CONF="$(mktemp)"
cat > "${TMP_CONF}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${PUBLIC_HOST};

    client_max_body_size 15m;

    location /.well-known/acme-challenge/ {
        root ${CERTBOT_WEBROOT};
    }

    location / {
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo mv "${TMP_CONF}" "${NGINX_SITE}"
sudo ln -sfn "${NGINX_SITE}" "${NGINX_ENABLED}"
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

cat <<EOF

HTTP setup complete.

Next steps:
1. Edit ${BACKEND_DIR}/.env
2. Set at least these values:
   ENVIRONMENT=production
   DEVICE_TOKEN_SECRET=<strong-random-secret>
   CARTESIA_API_KEY=<your-cartesia-key>
   GROQ_API_KEY=<your-groq-key-if-used>
   MOCK_TTS=false
   MOCK_PAYMENTS=false
   OPAY_API_BASE_URL=https://testapi.opaycheckout.com
   OPAY_CALLBACK_URL=http://${PUBLIC_HOST}/v1/topups/opay/webhook
   CORS_ORIGINS=["http://${PUBLIC_HOST}"]

3. Start the backend:
   bash deploy/run_backend_screen.sh

4. Check it:
   curl http://${PUBLIC_HOST}/health

If you later add HTTPS, update:
   OPAY_CALLBACK_URL=https://${PUBLIC_HOST}/v1/topups/opay/webhook
   CORS_ORIGINS=["https://${PUBLIC_HOST}"]
EOF
