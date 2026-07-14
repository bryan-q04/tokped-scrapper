// PM2 config for the HOME auth service (+ optionally the cloudflared tunnel).
// Run from the POC/ directory:
//   npm i -g pm2                                  # if you don't have it
//   $env:TOKPED_AUTH_TOKEN = "your-secret"        # PowerShell (or: set TOKPED_AUTH_TOKEN=...)
//   pm2 start ecosystem.config.js
//   pm2 save
// Prereqs: `python src/auth_service.py --login` done once, and deps installed in .venv.
const path = require("path");
const isWin = process.platform === "win32";
const py = path.join(__dirname, isWin ? ".venv/Scripts/python.exe" : ".venv/bin/python");

module.exports = {
  apps: [
    {
      name: "tokped-auth",
      script: path.join(__dirname, "src/auth_service.py"),
      interpreter: py,
      args: "--serve --host 127.0.0.1 --port 8765",
      cwd: __dirname,
      // TOKPED_AUTH_TOKEN is read from POC/.env (auto-loaded by settings.py via python-dotenv).
      // Keep it there — do NOT hard-code the secret here.
      autorestart: true,
      max_restarts: 10,
      time: true,
    },
    {
      // Optional: let PM2 run the tunnel too (or use `cloudflared service install` instead).
      name: "tokped-tunnel",
      script: "cloudflared",
      args: "tunnel run tokped-auth",
      interpreter: "none",
      autorestart: true,
      time: true,
    },
  ],
};
