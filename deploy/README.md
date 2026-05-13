## DropVoice server helpers

These scripts are for a fast single-server setup on Debian/Ubuntu.

### 1. Basic HTTP setup

Run this on the server from the repo root:

```bash
bash deploy/setup_server_http.sh 151.80.190.160
```

What it does:

- installs Python, nginx, and screen
- creates or reuses `.venv`
- installs backend requirements
- creates an nginx reverse-proxy on port 80
- creates `/var/www/certbot` for future ACME challenges

What it does not do:

- it does not fill in your backend secrets
- it does not start the backend process

### 2. Start the backend in screen

After editing `backend/.env`, run:

```bash
bash deploy/run_backend_screen.sh
```

Useful screen commands:

```bash
screen -r dropvoice
screen -ls
```

### 3. Optional HTTPS on the bare IP

If you want HTTPS on `151.80.190.160` without a domain, run:

```bash
bash deploy/setup_https_ip_cert.sh 151.80.190.160
```

Notes:

- This uses Let's Encrypt IP certificates.
- As of January 15, 2026, Let's Encrypt IP certs are generally available.
- As of March 11, 2026, Certbot added `--ip-address` support for these certs.
- These certs are short-lived, so renewal matters.

For live payments, HTTPS is the better path. If you only need a quick sandbox test, HTTP on the IP is the fastest setup.
