# Deployment — Lightsail runner + CI/CD (cookieless identity)

## Architecture (identity-first — current plan)
```
GitHub push ──▶ GitHub Actions ──SSH──▶ Lightsail VM ──▶ docker compose build
                                               │  (cron / web UI) docker compose run --rm runner
                                               ▼
Runner on VPS:  sends user_id param + Tkpd-Userid/Bd-Device-Id headers  ──▶ curated results
```
- **VPS = runner only** (curl_cffi, no browser) → the lowest/1 GB Lightsail is enough.
- **No cookie, no residential IP, no tunnel.** Tokopedia returns the real IQOS/TEREA result set
  when the request carries the account **identity** (`TOKPED_USER_ID` + `TOKPED_DEVICE_ID`), which
  are static — captured once from a browser, set in `.env`, and left alone.
- The old home auth-service + Cloudflare-tunnel + cookie path is now an **optional fallback**
  (see Part B) — only needed if Tokopedia ever forces a real session again.

> **Why cookieless:** the 4.7 KB session cookie combined with the identity headers gets
> HTTP/2-reset by Tokopedia, and — more importantly — the cookie isn't what curates the results;
> the `user_id`/device identity is. Verify locally any time with `python src/check_auth.py`.

---

## Part A — Lightsail VM (the runner)

1. Create a Lightsail **Linux, 1 GB** instance in a region near Indonesia (Singapore if Jakarta
   isn't offered for Lightsail). Paste [`deploy/lightsail-launch.sh`](deploy/lightsail-launch.sh)
   into the **"Launch script"** box — it installs Docker, adds a 2 GB swapfile, sets the
   timezone, and lets `ubuntu` run Docker. **That's the only VM prep** — GitHub Actions copies
   the code (`scp`) to `~/tokped-scraper` and builds it. No git/clone or deploy key on the VM.
2. After the **first successful deploy**, create `~/tokped-scraper/POC/.env` (NOT committed)
   with the static account identity (capture once from a browser — DevTools > the
   SearchProductV5Query request; see `.env.example`):
   ```
   TOKPED_USER_ID=<account id from params user_id / header Tkpd-Userid>
   TOKPED_DEVICE_ID=<header Bd-Device-Id>
   TOKPED_DISTRICT_ID=<params user_districtId>
   TOKPED_WEB_TOKEN=<secret to guard the web Run button>
   ```
   The runner auto-detects `TOKPED_USER_ID` and scrapes **cookieless**. No auth service needed.
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

## Part A2 — Web UI + domain + auto-HTTPS (Caddy)

A web UI (`webapp/`) lets you trigger scrapes and view/download reports. The `web` container
serves it internally on `:8000`; a **`caddy`** container terminates TLS and reverse-proxies to
it, provisioning + renewing the Let's Encrypt cert **automatically** — no nginx, no certbot.

1. **DNS**: add an **A record** `tokped-scrapper.virtual-app.my.id` → the VM's public **static** IP.
2. **Firewall**: open **ports 80 and 443** in Lightsail networking. *(done)*
3. **Email** (optional): change the ACME email in [`deploy/Caddyfile`](deploy/Caddyfile).
4. **`.env`**: add `TOKPED_WEB_TOKEN=<secret>` (guards the Run button) plus the identity vars
   (`TOKPED_USER_ID` / `TOKPED_DEVICE_ID` / `TOKPED_DISTRICT_ID`) to `~/tokped-scraper/POC/.env`.
5. **Bring it up** (GitHub Actions also runs this on every deploy):
   ```bash
   cd ~/tokped-scraper && sudo docker compose -f POC/docker-compose.yml up -d
   ```
   Caddy fetches the cert on the first request. Open
   **https://tokped-scrapper.virtual-app.my.id**, paste the token, hit **Run scrape**.

> If host **nginx** is running from a previous attempt, stop it so Caddy can bind 80/443:
> `sudo systemctl disable --now nginx`.
>
> Security: the token guards `POST /api/run`; the report/download views are open. For stricter
> access, put Cloudflare Access in front of the whole site.

---

## Part B — Home auth service (OPTIONAL FALLBACK — not needed for the identity path)

> You only need this if Tokopedia changes their API to require a real logged-in session again.
> While `check_auth.py` shows clean results with `TOKPED_USER_ID` set, skip this entire section
> and run `pm2 delete tokped-auth tokped-tunnel` to retire the tunnel + service.

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
