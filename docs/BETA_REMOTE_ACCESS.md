# Beta Remote Access Guide

## Hostnames

| Hostname                        | Purpose                           | Audience          |
|---------------------------------|-----------------------------------|--------------------|
| `www.memorysparkplay.fun`       | Main web UI for managing tracks   | Product owner      |
| `api.memorysparkplay.fun`       | API for mobile app sync           | Mobile app (beta)  |
| `ops.memorysparkplay.fun`       | Ops dashboard for diagnostics     | Product owner only |

All three hostnames route through a single Cloudflare Tunnel to the same
Docker container on port 8080. Path-based routing inside Flask separates
the concerns:

- `/` and `/api/*` — normal web UI and API (www + api hostnames)
- `/ops` and `/ops/api/*` — ops dashboard (ops hostname)

## Security Model

### Layer 1: Cloudflare Tunnel (transport)

All traffic flows through Cloudflare's network. No ports are open on the
VM's public IP. The tunnel is authenticated via a Cloudflare-managed token
stored in `/etc/cloudflared/config.yml`.

### Layer 2: Cloudflare Access (future — recommended for production)

When the product moves beyond beta, add Cloudflare Access policies:

- **www/api**: Allow public access (for customers)
- **ops**: Restrict to product owner's email via Cloudflare Access
  (one-time-PIN or SSO). This ensures ops is never exposed to end users.

During beta, all three hostnames are equally accessible. The ops token
(Layer 3) provides the access control.

### Layer 3: Ops Token (application)

The ops API endpoints require:

1. **Feature flag**: `MSS_OPS_ENABLED=1` environment variable must be set.
   When disabled, the ops page shows "Ops Disabled" and all API calls
   return 403.

2. **Shared secret**: Every ops API request must include:
   ```
   X-MSS-Ops-Token: <value of MSS_OPS_TOKEN env var>
   ```
   The HTML dashboard prompts for this token and sends it with every
   fetch request. The token is stored in `sessionStorage` (cleared when
   the browser tab closes).

### Setting the Token

On the VM:
```bash
# Generate a random token
export MSS_OPS_TOKEN=$(openssl rand -hex 24)
echo "Your ops token: $MSS_OPS_TOKEN"

# Add to environment (persists across restarts)
echo "MSS_OPS_ENABLED=1" >> ~/Projects/sound-machine/.env
echo "MSS_OPS_TOKEN=$MSS_OPS_TOKEN" >> ~/Projects/sound-machine/.env

# Restart to pick up the new env
cd ~/Projects/sound-machine
docker compose up -d
```

Share the token with the product owner via a secure channel (e.g., Signal,
1Password shared vault). Never send it in plain email.

## Ops Must Not Be Exposed to Future End Users

When the product opens to customers:

1. **Remove `ops.memorysparkplay.fun`** from the Cloudflare Tunnel config
   (or add a Cloudflare Access policy restricting it to internal users).

2. **Set `MSS_OPS_ENABLED=0`** in production to disable the feature
   entirely at the application level.

3. The ops code can remain in the codebase — it's inert when disabled.

## What the Ops Dashboard Shows

- **MSS Application**: App status, version (git SHA), server ID, uptime
- **Docker**: Container state, image, port health
- **Cloudflare Tunnel**: Config presence and preview (secrets redacted)
- **Disk & Memory**: Host disk usage and memory
- **Trackpacks**: Count, recent packs, published status
- **Logs**: View web or cloudflared logs (last 300 lines)
- **Snapshot**: Download a diagnostic archive (tar.gz) with configs,
  logs, and system info — all secrets redacted

## Quick Reference

```bash
# Check health from the host
./scripts/healthcheck.sh

# Generate a diagnostic snapshot
./scripts/ops_snapshot.sh /tmp/

# View ops dashboard in browser
open http://localhost:8080/ops
# (or https://ops.memorysparkplay.fun/ops)

# Curl the health API directly
curl -H "X-MSS-Ops-Token: YOUR_TOKEN" http://localhost:8080/ops/api/health
```
