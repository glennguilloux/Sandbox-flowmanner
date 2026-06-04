# VPS Rebuild Plan — Clean Slate After XMRig Compromise

**Date:** 2026-05-24
**Server:** IONOS VPS 74.208.115.142
**Reason:** Root-level XMRig miner compromise with 7 persistence layers found.
Attacker had root access via weak Plesk password. Login logs (wtmp/btmp) wiped.
Cannot guarantee system integrity. Full wipe and rebuild is the safe option.

**Estimated time:** 30-60 minutes
**Impact:** flowmanner.com goes offline during rebuild. Backend (homelab) is unaffected.

---

## Pre-requisites (already done)

- [x] All configs saved to `/opt/flowmanner/plans/vps-rebuild/`
  - docker-compose.yml
  - nginx-default.conf
  - .env.template (real values must be copied from homelab)
  - Dockerfile
  - wg0.conf (WireGuard config)
  - certbot-deploy-hook.sh
- [x] WireGuard config on homelab (`/etc/wireguard/wg0.conf`) is intact
- [x] Frontend source on homelab at `/home/glenn/FlowmannerV2-frontend/` is clean

---

## Phase 1: Wipe VPS (5 min)

1. Log into IONOS dashboard
2. Go to VPS > flowmanner.com > **Reinstall OS**
3. Select **Debian 12 (Bookworm)** or Debian 13 (Trixie)
4. Set root password to: `pXNSchwEJtJ^&wYz8fizZG&9`
5. Confirm reinstall -- wait for it to show "Running"
6. Test SSH: `sshpass -p 'pXNSchwEJtJ^&wYz8fizZG&9' ssh root@74.208.115.142`

---

## Phase 2: Harden OS (10 min)

```bash
# 2a. Update system
apt update && apt upgrade -y

# 2b. Create admin user (don't work as root)
adduser deploy
usermod -aG sudo deploy

# 2c. Set up SSH key auth (from homelab)
ssh-copy-id -i ~/.ssh/vps_flowmanner_new.pub deploy@74.208.115.142

# 2d. Harden SSH
cat > /etc/ssh/sshd_config.d/harden.conf <<EOF
PermitRootLogin prohibit-password
PasswordAuthentication no
MaxAuthTries 3
ClientAliveInterval 120
ClientAliveCountMax 3
EOF
systemctl restart sshd

# 2e. Install and configure firewall
apt install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw allow 51820/udp   # WireGuard
# Plesk (if installed): restrict to homelab only
ufw allow from 176.141.9.146 to any port 8443 proto tcp
ufw deny 8443/tcp
ufw --force enable
```

---

## Phase 3: Install Docker (5 min)

```bash
# 3a. Install Docker
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 3b. Verify
docker --version
docker compose version
```

---

## Phase 4: Install WireGuard (5 min)

```bash
# 4a. Install WireGuard
apt install -y wireguard

# 4b. Restore config
# Copy wg0.conf from /opt/flowmanner/plans/vps-rebuild/wg0.conf
# (do this from homelab via scp)
scp /opt/flowmanner/plans/vps-rebuild/wg0.conf root@74.208.115.142:/etc/wireguard/wg0.conf

# 4c. Enable WireGuard
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

# 4d. Verify tunnel
ping -c 3 10.99.0.3
```

---

## Phase 5: Deploy Frontend (10 min)

```bash
# 5a. Create project structure
mkdir -p /opt/flowmanner/{frontend,nginx,certs}

# 5b. Copy configs from homelab
# (run from homelab)
scp /opt/flowmanner/plans/vps-rebuild/docker-compose.yml root@74.208.115.142:/opt/flowmanner/
scp /opt/flowmanner/plans/vps-rebuild/nginx-default.conf root@74.208.115.142:/opt/flowmanner/nginx/default.conf
scp /opt/flowmanner/plans/vps-rebuild/.env.template root@74.208.115.142:/opt/flowmanner/.env
scp /opt/flowmanner/plans/vps-rebuild/Dockerfile root@74.208.115.142:/opt/flowmanner/frontend/Dockerfile

# 5c. IMPORTANT: Edit .env on VPS and fill in real secret values
# AUTH_SECRET, AUTH_GITHUB_ID, AUTH_GITHUB_SECRET must be the real values
# (sshpass masks them in output -- get them from homelab .env.local)
nano /opt/flowmanner/.env

# 5d. Rsync frontend source (from homelab)
rsync -avz --delete --progress \
  -e "sshpass -p 'pXNSchwEJtJ^&wYz8fizZG&9' ssh -o StrictHostKeyChecking=accept-new" \
  --exclude /node_modules \
  --exclude /.next/cache \
  --exclude /.git \
  --exclude /.env.local \
  /home/glenn/FlowmannerV2-frontend/ \
  root@74.208.115.142:/opt/flowmanner/frontend/

# 5e. Build and start
cd /opt/flowmanner
docker compose build frontend
docker compose up -d

# 5f. Verify
docker compose ps
docker logs flowmanner-frontend --tail 10
```

---

## Phase 6: SSL Certificates (10 min)

### Option A: Fresh Let's Encrypt (recommended -- clean trust chain)

```bash
# 6a. Install certbot
apt install -y certbot

# 6b. Create webroot for challenges
mkdir -p /var/www/certbot

# 6c. Get certificate (nginx must be running on port 80)
certbot certonly --webroot \
  -w /var/www/certbot \
  -d flowmanner.com \
  -d www.flowmanner.com \
  --email glennguilloux@gmail.com \
  --agree-tos \
  --non-interactive

# 6d. Copy certs to project
mkdir -p /opt/flowmanner/certs
cp /etc/letsencrypt/live/flowmanner.com/fullchain.pem /opt/flowmanner/certs/
cp /etc/letsencrypt/live/flowmanner.com/privkey.pem /opt/flowmanner/certs/

# 6e. Set up auto-renewal hook
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cp /opt/flowmanner/plans/vps-rebuild/certbot-deploy-hook.sh /etc/letsencrypt/renewal-hooks/deploy/flowmanner.sh
chmod +x /etc/letsencrypt/renewal-hooks/deploy/flowmanner.sh

# 6f. Restart nginx with SSL
docker compose restart nginx
```

### Option B: Copy existing certs from old VPS (NOT recommended -- might be compromised)

Skip this. Get fresh certs.

---

## Phase 7: Plesk (Optional) (15 min)

**Think hard about whether you need Plesk at all.** It was the attack vector.
If you only use it for cert management, certbot alone is sufficient (Phase 6).

If you DO need Plesk:

```bash
# 7a. Install Plesk
wget -O - https://autoinstall.plesk.com/one-click-installer | sh

# 7b. Set strong admin password
plesk bin init_conf --init -passwd 'pXNSchwEJtJ^&wYz8fizZG&9'

# 7c. RESTRICT ACCESS -- only from homelab
# Already done via UFW in Phase 2, but also restrict in Plesk itself:
# Tools & Settings > Restrict Access to Plesk > Allow from: 176.141.9.146

# 7d. Disable Apache (we use Docker nginx)
# Tools & Settings > Services Management > Stop Apache
# Or: plesk bin http2_pref disable
```

---

## Phase 8: Final Verification (5 min)

```bash
# 8a. Check all services
docker compose ps
wg show
ufw status

# 8b. Test site
curl -sk https://flowmanner.com/ -o /dev/null -w 'HTTPS: %{http_code}\n'
curl -s http://10.99.0.3:8000/api/health

# 8c. Security check
ps aux | grep -E 'xmrig|kworker|kryptex|miner' | grep -v grep
crontab -l 2>&1
lsattr -R /etc/ 2>/dev/null | grep -E '[ia]'
grep -r 'xmrig\|kworker' /etc/ 2>/dev/null

# 8d. Check for immutable files
lsattr -R /root /usr/local/bin /var/tmp /tmp 2>/dev/null | grep -E '[ia]'

# 8e. Browser test
# Open https://flowmanner.com in browser
# Log in with: glennguilloux@gmail.com / Flowmanner2026!
```

---

## Phase 9: Update Homelab References (2 min)

```bash
# 9a. Update deploy script password (if changed)
# Already uses SSH key via vps_flowmanner_new

# 9b. Rebuild known_hosts (new OS = new host key)
ssh-keygen -R 74.208.115.142
ssh-keyscan -H 74.208.115.142 >> ~/.ssh/known_hosts

# 9c. Test deploy script
bash /opt/flowmanner/deploy-frontend.sh --dry-run
```

---

## Security Checklist (from this incident)

| Lesson | Action |
|--------|--------|
| Weak Plesk password | Strong password set |
| Plesk open to world | UFW restrict to homelab IP only |
| No user isolation | Created `deploy` user with sudo |
| Root SSH with password | Root SSH key-only, password disabled |
| No immutable file monitoring | Added to verification checklist |
| No login monitoring | Consider installing fail2ban + logwatch |

## What Changed vs Old Setup

- No more Plesk Apache (Docker nginx handles everything)
- SSH key-only auth (no passwords for SSH)
- Separate `deploy` user instead of working as root
- UFW blocks Plesk port from non-homelab IPs
- Deploy script uses `--exclude /node_modules` (leading slash) to preserve standalone deps
- BACKEND_URL correctly set to 10.99.0.3:8000 (WireGuard) not Docker hostname

## Rollback

If rebuild fails, IONOS dashboard has a snapshot/backup feature that can restore the previous state. But given the compromise, this should be a last resort only.

## Files in this plan directory

```
/opt/flowmanner/plans/vps-rebuild/
  PLAN.md                  -- This file
  docker-compose.yml       -- Docker services
  nginx-default.conf       -- Nginx reverse proxy config
  .env.template            -- Env vars (fill in real secrets from homelab .env.local)
  Dockerfile               -- Frontend container build
  wg0.conf                 -- WireGuard tunnel config
  certbot-deploy-hook.sh   -- SSL cert auto-renewal hook
```
