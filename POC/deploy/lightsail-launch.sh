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

# 3) Docker + compose plugin + git.
apt-get update
apt-get install -y --no-install-recommends docker.io docker-compose-plugin git ca-certificates
systemctl enable --now docker

# 4) Let the default user (ubuntu) run docker without sudo.
usermod -aG docker ubuntu || true

# 5) Deploy target used by the GitHub Actions workflow.
install -d -o ubuntu -g ubuntu /opt/tokped-scraper

echo "bootstrap done"

# ---------------------------------------------------------------------------
# MANUAL, once, after boot (these involve secrets/auth — keep them OUT of here):
#   1. Add a read-only DEPLOY KEY so the VM can pull the repo:
#        sudo -u ubuntu ssh-keygen -t ed25519 -f /home/ubuntu/.ssh/id_ed25519 -N ''
#        # add the .pub to GitHub repo -> Settings -> Deploy keys (read-only)
#        sudo -u ubuntu git clone git@github.com:<you>/<repo>.git /opt/tokped-scraper
#   2. Create /opt/tokped-scraper/POC/.env :
#        TOKPED_CRED_URL=https://auth.example.com
#        TOKPED_CRED_TOKEN=<same secret as the home auth service>
#   3. Add the daily cron (see DEPLOY.md Part A step 5).
# ---------------------------------------------------------------------------
