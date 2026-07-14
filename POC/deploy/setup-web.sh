#!/bin/bash
# One-time on the VM (run as root: `sudo bash POC/deploy/setup-web.sh`).
# Prereqs: (1) DNS A record  tokped-scrapper.virtual-app.my.id -> this VM's public IP,
#          (2) Lightsail firewall allows ports 80 and 443,
#          (3) the `web` container is running (docker compose up -d web) on 127.0.0.1:8000.
# Installs nginx + certbot, reverse-proxies the domain to the app, and gets a Let's Encrypt cert.
set -euxo pipefail

DOMAIN="tokped-scrapper.virtual-app.my.id"
EMAIL="admin@${DOMAIN}"   # change to a real email for cert-expiry notices

apt-get update
apt-get install -y nginx certbot python3-certbot-nginx

cat >/etc/nginx/sites-available/tokped <<EOF
server {
    listen 80;
    server_name ${DOMAIN};
    client_max_body_size 10m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 3600;   # scrapes can run for minutes
    }
}
EOF

ln -sf /etc/nginx/sites-available/tokped /etc/nginx/sites-enabled/tokped
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Obtain + install the cert and enable auto HTTP->HTTPS redirect. Certbot adds a renewal timer.
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" --redirect

echo "web setup done -> https://${DOMAIN}"
