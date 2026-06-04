# Flowmanner VPS Rebuild — Executed Runbook

**Date:** 2026-05-24
**VPS:** 74.208.115.142 (IONOS)
**OS:** Debian 13 (Trixie)
**Time:** ~25 minutes from wipe to live SSL

---

## Phase 1: IONOS Dashboard — Wipe (user action)

1. Log into IONOS dashboard
2. Select VPS → Reinstall OS
3. Choose Debian 13 (Trixie)
4. Set root password: `68bCX3xb5DosTyI`
5. Wait ~5 min for "Running" status

---

## Phase 2: OS Hardening

```bash
# SSH as root (password auth until keys are set up)
ssh root@74.208.115.142

# Update system
apt update && apt upgrade -y

# Install essentials
apt install -y ufw curl wget git gnupg ca-certificates wireguard

# Create deploy user
useradd -m -s /bin/bash deploy
usermod -aG sudo deploy
echo "deploy ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/deploy

# Setup SSH key auth
mkdir -p /root/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBTXMy+maE5OMjF5vp3FwHIlRLuF1imtoBP1pB5M8SIQ orchestrator-vps" > /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Harden SSH (key-only, no root password)
cat > /etc/ssh/sshd_config.d/harden.conf <<'EOF'
PermitRootLogin prohibit-password
PasswordAuthentication no
MaxAuthTries 3
ClientAliveInterval 120
ClientAliveCountMax 3
EOF
systemctl restart sshd

# Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 51820/udp
ufw allow from 176.141.9.146 to any port 8443 proto tcp
ufw deny 8443/tcp
ufw deny 8880/tcp
ufw allow in on wg0          # CRITICAL: allow tunnel traffic
ufw --force enable
```

---

## Phase 3: Docker

```bash
# Install Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian trixie stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

---

## Phase 4: WireGuard Tunnel

```bash
# Create WireGuard config
cat > /etc/wireguard/wg0.conf <<'WG'
[Interface]
Address = 10.99.0.1/24
ListenPort = 51820
PrivateKey = <REDACTED-SEE-HOMELAB>

[Peer]
PublicKey = AdZG7G7cwaYTIUB9CyF2FxxwQWUyQLab+VWIkM9rMEI=
AllowedIPs = 10.99.0.3/32
Endpoint = 176.141.9.146:51820
PersistentKeepalive = 5
WG

systemctl enable --now wg-quick@wg0

# Verify
ping -c 2 10.99.0.3
```

---

## Phase 5: Project Structure & Configs

```bash
# Create directories
mkdir -p /opt/flowmanner/{frontend,nginx,certs}

# docker-compose.yml
cat > /opt/flowmanner/docker-compose.yml <<'DC'
services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: flowmanner-frontend
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - BACKEND_URL=http://10.99.0.3:8000
      - AUTH_TRUST_HOST=true
    expose:
      - "3000"
    networks:
      - flowmanner

  nginx:
    image: nginx:alpine
    container_name: flowmanner-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - /var/www/certbot:/var/www/certbot:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - frontend
    networks:
      - flowmanner

networks:
  flowmanner:
    driver: bridge
DC

# .env (real secrets filled in)
cat > /opt/flowmanner/.env <<'ENV'
AUTH_SECRET=70bf89ee4c8773ee3a4d3961a1e03f1f8b3c9e4d2a6f1c5e7d0b9a2f8e3c5f1d
AUTH_GITHUB_ID=Ov23liwIKWZgJI51qmbh
AUTH_GITHUB_SECRET=f126450d62b9aa10edaf28027f8a7b806c8e8da2
NEXTAUTH_URL=https://flowmanner.com
BACKEND_URL=http://10.99.0.3:8000
NEXT_PUBLIC_API_URL=https://flowmanner.com/api
AUTH_TRUST_HOST=true
ENV

# nginx config (from homelab /opt/flowmanner/plans/vps-rebuild/nginx-default.conf)
# ... written to /opt/flowmanner/nginx/default.conf ...

# Dockerfile (from homelab /opt/flowmanner/plans/vps-rebuild/Dockerfile)
# ... written to /opt/flowmanner/frontend/Dockerfile ...
```

**Nginx config key points:**
- Port 80 → 301 redirect to HTTPS
- Port 443 → SSL termination, routes:
  - `/api/auth/*` → frontend:3000 (NextAuth)
  - `/api/*` → 10.99.0.3:8000 (backend via WireGuard)
  - `/ws` → 10.99.0.3:8000 (WebSocket via WireGuard)
  - `/*` → frontend:3000 (Next.js SSR)
- Blocked paths: `.env`, `.git`, `wp-admin`, `phpmyadmin`

---

## Phase 6: Disable Plesk Apache

```bash
# Apache and Plesk web server hog port 80/443
systemctl disable --now apache2 sw-cp-server
```

---

## Phase 7: Rsync Frontend + Build

```bash
# From homelab:
rsync -avz --delete --progress \
  -e "ssh -i ~/.ssh/vps_flowmanner_new -o StrictHostKeyChecking=accept-new" \
  --exclude /node_modules \
  --exclude /.next/cache \
  --exclude /.git \
  --exclude /.env.local \
  /home/glenn/FlowmannerV2-frontend/ \
  root@74.208.115.142:/opt/flowmanner/frontend/

# Then on VPS:
cd /opt/flowmanner
docker compose build frontend
docker compose up -d
```

**⚠️ CRITICAL: `--exclude /node_modules` (leading slash)**
The leading `/` anchors the exclude to the transfer root. Without it, `--exclude node_modules` also strips `.next/standalone/node_modules/` which contains the runtime `next`, `react`, etc. This caused the "Cannot find module 'next'" crash on the old VPS.

---

## Phase 8: SSL Certificates (Let's Encrypt)

```bash
# Install certbot
apt install -y certbot

# Create webroot
mkdir -p /var/www/certbot

# Get certs (nginx must be running on port 80)
certbot certonly --webroot \
  -w /var/www/certbot \
  -d flowmanner.com \
  -d www.flowmanner.com \
  --email glennguilloux@gmail.com \
  --agree-tos \
  --non-interactive

# Copy to project
cp /etc/letsencrypt/live/flowmanner.com/fullchain.pem /opt/flowmanner/certs/
cp /etc/letsencrypt/live/flowmanner.com/privkey.pem /opt/flowmanner/certs/

# Restart nginx
docker compose restart nginx

# Set up auto-renewal hook
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/flowmanner.sh <<'HOOK'
#!/bin/bash
cp /etc/letsencrypt/live/flowmanner.com/fullchain.pem /opt/flowmanner/certs/
cp /etc/letsencrypt/live/flowmanner.com/privkey.pem /opt/flowmanner/certs/
docker restart flowmanner-nginx
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/flowmanner.sh
```

---

## Phase 9: Verification

```bash
# Containers
docker compose ps
# Expected: frontend Up, nginx Up, ports 80/443 mapped

# Site (no browser SSL warning)
curl -sSf https://flowmanner.com/ -o /dev/null -w '%{http_code}\n'
# Expected: 307

# Backend
curl -s http://10.99.0.3:8000/api/health
# Expected: {"status":"ok",...}

# WireGuard
wg show
# Expected: peer handshake, transfer bytes

# Security scan
ps aux | grep xmrig || echo "CLEAN"
crontab -l 2>&1 || echo "EMPTY"
lsattr -R /etc/ /root/ /var/tmp/ 2>/dev/null | grep '[ia]' || echo "CLEAN"
grep -r 'xmrig\|kworker' /etc/ 2>/dev/null || echo "CLEAN"

# Cert info
openssl s_client -connect flowmanner.com:443 -servername flowmanner.com </dev/null 2>/dev/null | openssl x509 -noout -dates
# Expected: Let's Encrypt, expires Aug 22 2026
```

---

## Final System State

| Component | Value |
|-----------|-------|
| OS | Debian 13 (Trixie) |
| Root password | 68bCX3xb5DosTyI |
| SSH | Key-only, `PermitRootLogin prohibit-password` |
| SSH key | `vps_flowmanner_new` (ed25519, "orchestrator-vps") |
| Docker | 29.5.2, Compose v5.1.4 |
| WireGuard IP | 10.99.0.1 |
| Firewall | UFW: 22,80,443,51820 open; 8443/8880 locked to homelab |
| SSL | Let's Encrypt, auto-renew via certbot.timer |
| Deploy user | `deploy` (sudo, nopasswd) |
| Plesk | NOT installed |
| Project root | `/opt/flowmanner/` |

## Credentials

| What | Where |
|------|-------|
| VPS SSH | `ssh -i ~/.ssh/vps_flowmanner_new root@74.208.115.142` |
| Flowmanner login | glennguilloux@gmail.com / Flowmanner2026! |
| Plesk | Not installed. If needed later, install and lock to 176.141.9.146 |

## Files Saved for Future Rebuilds

All configs saved at `/opt/flowmanner/plans/vps-rebuild/` on the homelab:
- docker-compose.yml
- nginx-default.conf
- Dockerfile
- wg0.conf
- certbot-deploy-hook.sh
- .env.template (fill in real values from `.env.local`)
- PLAN.md (original plan)
