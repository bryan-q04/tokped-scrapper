#!/bin/bash
# Lightsail LAUNCH SCRIPT — paste into the "Launch script" box when creating the instance
# (runs once as root on first boot). Bootstraps the host so GitHub Actions can deploy to it.
#
# It intentionally does NOT: store secrets, or clone a private repo — launch scripts are
# visible in the Lightsail console. Do those two things manually after boot (see the tail).
set -euxo pipefail

# 1) Swap — important on 512 MB / 1 GB instances so the build/report don't OOM.
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 2) Timezone (nice for correct scrape timestamps).
timedatectl set-timezone Asia/Jakarta || true

# 3) Docker engine + compose v2 plugin (official script — the Ubuntu repo lacks the plugin).
apt-get update
apt-get install -y --no-install-recommends curl ca-certificates git
if ! command -v docker >/dev/null 2>&1; then curl -fsSL https://get.docker.com | sh; fi
systemctl enable --now docker

# 4) Let the default user (ubuntu) run docker without sudo.
usermod -aG docker ubuntu || true

echo "bootstrap done"

# ---------------------------------------------------------------------------
# That's all the VM needs — GitHub Actions copies the code to ~/tokped-scraper and builds.
# MANUAL, once, after the first successful deploy (involves a secret, keep it OUT of here):
#   1. Create ~/tokped-scraper/POC/.env :
#        TOKPED_CRED_URL=https://auth.example.com
#        TOKPED_CRED_TOKEN=<same secret as the home auth service>
#   2. Add the daily cron (see DEPLOY.md Part A).
# ---------------------------------------------------------------------------
