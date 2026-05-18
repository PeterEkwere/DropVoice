#!/usr/bin/env bash
set -euo pipefail

PUBLIC_IP="${1:-${PUBLIC_IP:-}}"
API_PORT="${API_PORT:-8000}"
SITE_NAME="dropvoice"
NGINX_SITE="/etc/nginx/sites-available/${SITE_NAME}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${SITE_NAME}"
CERTBOT_WEBROOT="/var/www/certbot"
RENEW_HOOK="/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh"

if [[ -z "${PUBLIC_IP}" ]]; then
  echo "Usage: bash deploy/setup_https_ip_cert.sh <public-ip>"
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx is not installed. Run the HTTP setup script first."
  exit 1
fi

sudo mkdir -p "${CERTBOT_WEBROOT}"

if ! command -v snap >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y snapd
fi

sudo snap install core || true
sudo snap refresh core
sudo snap install --classic certbot || true
sudo ln -sfn /snap/bin/certbot /usr/local/bin/certbot

sudo certbot certonly \
  --webroot \
  --webroot-path "${CERTBOT_WEBROOT}" \
  --ip-address "${PUBLIC_IP}" \
  --preferred-profile shortlived \
  --agree-tos \
  --register-unsafely-without-email \
  --non-interactive

TMP_CONF="$(mktemp)"
cat > "${TMP_CONF}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${PUBLIC_IP};

    client_max_body_size 15m;

    location /.well-known/acme-challenge/ {
        root ${CERTBOT_WEBROOT};
    }

    location / {
        return 308 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${PUBLIC_IP};

    client_max_body_size 15m;

    ssl_certificate /etc/letsencrypt/live/${PUBLIC_IP}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${PUBLIC_IP}/privkey.pem;

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
sudo nginx -t
sudo systemctl reload nginx

TMP_HOOK="$(mktemp)"
cat > "${TMP_HOOK}" <<'EOF'
#!/usr/bin/env bash
systemctl reload nginx
EOF

sudo mkdir -p "$(dirname "${RENEW_HOOK}")"
sudo mv "${TMP_HOOK}" "${RENEW_HOOK}"
sudo chmod +x "${RENEW_HOOK}"

cat <<EOF

HTTPS setup complete for ${PUBLIC_IP}.

Now update backend/.env:
  OPAY_CALLBACK_URL=https://${PUBLIC_IP}/v1/topups/opay/webhook
  CORS_ORIGINS=["https://${PUBLIC_IP}"]

Verify:
  curl https://${PUBLIC_IP}/health

Note:
  Let's Encrypt IP certificates are short-lived. Renewals matter.
EOF
