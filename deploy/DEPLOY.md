# Deploy — `wspsquad-polyfintech.ngyuhang.com` (VPS + Cloudflare Tunnel + login gate)

Hosts the full stack on a VPS, 24/7, behind a username/password gate, reachable
only via a Cloudflare Tunnel. **No inbound ports are opened** and the VPS IP is
never exposed — cloudflared dials out to Cloudflare, and a login is required
before the page *or* the API loads.

```
Browser ──HTTPS──▶ Cloudflare edge ──tunnel──▶ cloudflared ──▶ Caddy (:8080, Basic Auth)
                                                                  ├─ /api/*  ▶ uvicorn (127.0.0.1:8000)
                                                                  └─ /       ▶ frontend/dist (SPA)
```

Assumes **Ubuntu 22.04/24.04** and that `ngyuhang.com` is already on Cloudflare
(it is). Adjust the user (`ubuntu`) and paths if yours differ — they appear in
the Caddyfile, the cloudflared config, and all three systemd units.

The login is **HTTP Basic Auth at Caddy**, with credentials read from `.env`
(`BASIC_AUTH_USER` and `BASIC_AUTH_HASH`, the bcrypt hash). The username and
password live **only in your `.env`** — they are intentionally not written into
this committed file.

---

## 0. Prerequisites
- A VPS you can SSH into (this guide uses user `ubuntu`, home `/home/ubuntu`).
- `ngyuhang.com` managed in Cloudflare DNS.
- The `.env` file (NOT in git) copied to the VPS — it carries the API keys **and**
  the `BASIC_AUTH_*` values. Keep it at the repo root: `WSP-Squad-Polyfintech-2026/.env`.

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
- Visit **https://wspsquad-polyfintech.ngyuhang.com** → browser asks for login →
  enter the `BASIC_AUTH_USER` + password from your `.env` → dashboard loads.
- The chat works (it carries the same login automatically on its `/api` calls).

---

## Updating later (after a `git push`)
```bash
cd /home/ubuntu/WSP-Squad-Polyfintech-2026
git pull
. .venv/bin/activate && pip install -r backend/requirements.txt && deactivate
cd frontend && npm ci && npm run build && cd ..
sudo systemctl restart wspsquad-backend wspsquad-caddy
```

## Changing the login
Regenerate the hash and update `.env`, then restart Caddy:
```bash
caddy hash-password --plaintext 'NEW_PASSWORD'   # paste output into BASIC_AUTH_HASH
sudo systemctl restart wspsquad-caddy
```

## Security notes
- **Everything is gated.** Basic Auth covers the SPA and `/api` (including the
  agent), so nobody can hit your OpenRouter / Bright Data keys without the login.
- **Nothing is exposed.** Backend and Caddy bind to localhost; the only path in
  is the tunnel. You can leave the VPS firewall closed to all inbound except SSH.
- **`.env` carries real secrets** (API keys + the auth hash). Keep it `chmod 600`,
  never commit it, and be deliberate about who you hand it to.
- If a credential ever leaks, rotate the OpenRouter / Bright Data keys and change
  the Basic Auth password.
