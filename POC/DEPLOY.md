# Deployment — Lightsail runner + home auth service + CI/CD

## Architecture (Variant A — current plan)
```
GitHub push ──▶ GitHub Actions ──SSH──▶ Lightsail VM ──▶ docker compose build
                                               │  (cron) docker compose run --rm runner
                                               ▼
HOME machine: auth_service.py --serve  ──cloudflared──▶ https://auth.example.com  (Cloudflare)
Runner on VPS:  TOKPED_CRED_URL=https://auth.example.com ──GET /cred──▶ authenticated cookie
```
- **VPS = runner only** (curl_cffi, no browser) → the lowest/1 GB Lightsail is enough.
- **Home = auth** (residential IP): one-time headful login, serves the cookie over a Cloudflare Tunnel.

---

## Part A — Lightsail VM (the runner)

1. Create a Lightsail **Linux, 1 GB** instance in a region near Indonesia (Singapore if Jakarta
   isn't offered for Lightsail). Paste [`deploy/lightsail-launch.sh`](deploy/lightsail-launch.sh)
   into the **"Launch script"** box — it installs Docker, adds a 2 GB swapfile, sets the
   timezone, and lets `ubuntu` run Docker. **That's the only VM prep** — GitHub Actions copies
   the code (`scp`) to `~/tokped-scraper` and builds it. No git/clone or deploy key on the VM.
2. After the **first successful deploy**, create `~/tokped-scraper/POC/.env` (NOT committed),
   pointing the runner at the home auth service:
   ```
   TOKPED_CRED_URL=https://auth.example.com
   TOKPED_CRED_TOKEN=<same secret as the home service>
   ```
3. Manual test run on the VM:
   ```bash
   cd ~/tokped-scraper
   docker compose -f POC/docker-compose.yml run --rm runner            # anonymous products
   docker compose -f POC/docker-compose.yml run --rm runner --show-adult  # TEREA (needs auth)
   ```
4. Schedule it with host cron (`crontab -e`), e.g. daily 03:00 WIB:
   ```
   0 3 * * * cd ~/tokped-scraper && docker compose -f POC/docker-compose.yml run --rm runner >> ~/tokped.log 2>&1
   ```
   Outputs land in `POC/data/` (SQLite, `export_<date>.csv`, `sellers_<date>.csv`, HTML report).

---

## Part B — Home auth service (residential IP)

1. On your home machine, set up the full env (this one needs Playwright):
   ```bash
   cd POC && python -m venv .venv && source .venv/Scripts/activate   # or bin/activate
   pip install -r requirements.txt && python -m playwright install chromium
   ```
2. **One-time login** (headful — you do OTP + age/KTP verification):
   ```bash
   python src/auth_service.py --login
   ```
3. Run the service (keep the token secret; must equal `TOKPED_CRED_TOKEN` on the VPS):
   ```bash
   TOKPED_AUTH_TOKEN=<secret> python src/auth_service.py --serve --host 127.0.0.1 --port 8765
   ```
   Optional `systemd` unit so it restarts on boot (`/etc/systemd/system/tokped-auth.service`):
   ```ini
   [Unit]
   Description=Tokopedia auth service
   After=network-online.target
   [Service]
   WorkingDirectory=/home/you/tokped-scraper/POC
   Environment=TOKPED_AUTH_TOKEN=CHANGE_ME
   ExecStart=/home/you/tokped-scraper/POC/.venv/bin/python src/auth_service.py --serve
   Restart=always
   [Install]
   WantedBy=multi-user.target
   ```
4. **Cloudflare Tunnel** exposes `localhost:8765` as `auth.example.com` (no open ports):
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create tokped-auth
   cloudflared tunnel route dns tokped-auth auth.example.com
   ```
   `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: <TUNNEL_ID>
   credentials-file: /home/you/.cloudflared/<TUNNEL_ID>.json
   ingress:
     - hostname: auth.example.com
       service: http://localhost:8765
     - service: http_status:404
   ```
   `cloudflared tunnel run tokped-auth` (or install as a service).
5. **Lock it down with Cloudflare Access** (Zero Trust): add an application for
   `auth.example.com` with a **service-token** policy, and send those token headers from the VPS.
   A leaked logged-in cookie = account takeover — do NOT rely on the bearer token alone.

---

## Part C — GitHub Actions CI/CD

Workflow: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml). On push to `main`
it runs a syntax check + offline smoke test, then SSHes into the VM and rebuilds.

Add these repo **Secrets** (Settings → Secrets and variables → Actions):
- `LIGHTSAIL_HOST` — VM public IP
- `LIGHTSAIL_USER` — e.g. `ubuntu`
- `LIGHTSAIL_SSH_KEY` — the private key for that VM

Push to `main` → CI tests → deploys. Cron on the VM then runs the scrape on schedule.

---

## Security checklist
- `.env` and `POC/data/` are gitignored — never commit secrets or the cookie/profile.
- Cloudflare Access **in front of** `auth.example.com` + the bearer token (defence in depth).
- Burner Tokopedia account for the authenticated (TEREA) path.
- Keep request rate low + jitter; the runner already re-pulls a fresh cred on a 403.

---

## Variant B fallback (if Variant A gets re-challenged from the VPS IP)
If the datacenter IP breaks the anti-bot layer (403 / empty TEREA from the VM), flip roles:
- **Runner runs on the home machine** (residential IP) — it already supports `--auto-cookie`
  (needs Playwright/Chromium there) or the local auth cookie.
- **VPS becomes the orchestrator** — schedules/triggers the home runner and stores/serves the
  results. The same code runs; only *where* it executes and *how* it's triggered changes.
No rewrite needed — the runner is location-agnostic about where it runs.
