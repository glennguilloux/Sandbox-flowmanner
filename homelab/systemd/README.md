# Homelab systemd units

Systemd unit files for services that run directly on the homelab host (not in
Docker). Each file here is meant to be symlinked or copied into
`/etc/systemd/system/` and activated with `systemctl`.

## llama-server-light.service

Qwen2.5-1.5B-Instruct-Q4_K_M served by llama-server on port 11435.
Used as a cheap/fast reviewer fallback for the background review task.
Different from the 27B server on :11434 — this one is for short, structured
JSON extraction (memory entries, tags, supersede decisions) where the 27B
would be overkill.

GGUF: `/mnt/apps/models/light/qwen2.5-1.5b-instruct-q4_k_m.gguf` (1.04 GB)

Install:

```bash
sudo cp /opt/flowmanner/homelab/systemd/llama-server-light.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now llama-server-light.service
sudo systemctl status llama-server-light.service
```

Verify:

```bash
curl -sS http://127.0.0.1:11435/v1/models | head -c 200
# Expect: {"models":[{"name":"qwen2.5-1.5b-instruct-q4_k_m.gguf",...
```

UFW (homelab default is deny-incoming):

The backend container reaches the host's llama-server via the bridge IP
(`10.0.4.1:<port>` from a container on `glenn_workflows-web`). UFW blocks
new ports by default. Add an explicit allow rule — UFW-native form
survives reboot and `ufw reload`, raw `iptables -I INPUT` does not:

```bash
sudo ufw allow 11435/tcp comment "llama.cpp 1.5B light reviewer"
```

Test from inside a container after the rule is in:

```bash
docker compose exec backend curl -sS http://10.0.4.1:11435/v1/models
```
