# Deploy — `wspsquad-polyfintech.ngyuhang.com` (VPS + Cloudflare Tunnel)

Hosts the full stack on a VPS, 24/7, reachable only via a Cloudflare Tunnel.
**No inbound ports are opened** and the VPS IP is never exposed — cloudflared
dials out to Cloudflare. The site is **public** (no login); abuse is bounded by
a per-day cap on AI messages (below), and the API keys stay server-side only.

```
Browser ──HTTPS──▶ Cloudflare edge ──tunnel──▶ cloudflared ──▶ Caddy (:8080)
                                                                  ├─ /api/*  ▶ uvicorn (127.0.0.1:8000)
                                                                  └─ /       ▶ frontend/dist (SPA)
```

Assumes **Ubuntu 22.04/24.04** and that `ngyuhang.com` is already on Cloudflare
(it is). Adjust the user (`ubuntu`) and paths if yours differ — they appear in
the Caddyfile, the cloudflared config, and all three systemd units.

There is **no login**. The AI agent is rate-limited to `AGENT_DAILY_LIMIT`
messages per day (default 100) to bound API cost; everything else is open. API
keys are used only by the backend and are never sent to the browser.

---

## 0. Prerequisites
- A VPS you can SSH into (this guide uses user `ubuntu`, home `/home/ubuntu`).
- `ngyuhang.com` managed in Cloudflare DNS.
- The `.env` file (NOT in git) copied to the VPS — it carries the API keys. Keep
  it at the repo root: `WSP-Squad-Polyfintech-2026/.env`.

## 1. Clone the repo + drop in .env
```bash
cd /home/ubuntu
git clone https://github.com/fountainnnnn/WSP-Squad-Polyfintech-2026.git
cd WSP-Squad-Polyfintech-2026
# copy your .env here (scp from your laptop, or paste it):
#   scp .env ubuntu@<vps>:/home/ubuntu/WSP-Squad-Polyfintech-2026/.env
chmod 600 .env
```

## 2. Backend (Python venv)
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r backend/requirements.txt uvicorn
deactivate
```
> The app builds its dashboard JSON on first start if missing, but `out/` is
> already committed, so it comes up immediately.

## 3. Frontend (build static)
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
cd frontend && npm ci && npm run build && cd ..
# produces frontend/dist  (served by Caddy)
```

## 4. Install Caddy
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
sudo systemctl disable --now caddy   # we run our OWN caddy unit, not the default site
```

## 5. Install cloudflared + create the tunnel
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
sudo install cloudflared /usr/bin/cloudflared && rm cloudflared

cloudflared tunnel login                 # opens a URL; authorize the ngyuhang.com zone
cloudflared tunnel create wspsquad       # prints a TUNNEL_ID and writes ~/.cloudflared/<TUNNEL_ID>.json
cloudflared tunnel route dns wspsquad wspsquad-polyfintech.ngyuhang.com   # creates the CNAME in Cloudflare
```
Then install the config:
```bash
cp deploy/cloudflared.config.yml ~/.cloudflared/config.yml
sed -i "s/TUNNEL_ID/<paste the id here>/g" ~/.cloudflared/config.yml
```

## 6. Install + start the services
```bash
sudo cp deploy/systemd/wspsquad-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wspsquad-backend wspsquad-caddy wspsquad-tunnel
```
Check them:
```bash
systemctl status wspsquad-backend wspsquad-caddy wspsquad-tunnel --no-pager
journalctl -u wspsquad-tunnel -n 30 --no-pager
```

## 7. Verify
- Visit **https://wspsquad-polyfintech.ngyuhang.com** → the dashboard loads (no login).
- The AI agent works; after `AGENT_DAILY_LIMIT` messages in a day it returns a
  "daily limit reached" message until the next UTC day.

---

## Updating later (after a `git push`)
```bash
cd /home/ubuntu/WSP-Squad-Polyfintech-2026
git pull
. .venv/bin/activate && pip install -r backend/requirements.txt && deactivate
cd frontend && npm ci && npm run build && cd ..
sudo systemctl restart wspsquad-backend wspsquad-caddy
```

## Changing the rate limit
Set `AGENT_DAILY_LIMIT` in `.env` (default 100), then restart the backend:
```bash
sudo systemctl restart wspsquad-backend
```

## Security notes
- **API cost is bounded** by the agent's daily message cap; the dashboard/data
  endpoints are cheap static reads and stay open.
- **Keys never reach the browser.** OpenRouter / Bright Data keys are used only by
  the backend; the frontend calls `/api/*` and never sees them.
- **Nothing is exposed.** Backend and Caddy bind to localhost; the only path in
  is the tunnel. You can leave the VPS firewall closed to all inbound except SSH.
- **`.env` carries real secrets** (API keys). Keep it `chmod 600`, never commit it,
  and rotate the keys if one ever leaks.
