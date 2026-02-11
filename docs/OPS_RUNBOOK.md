# MSS Ops Runbook

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Internet                                               │
│                                                         │
│  Users ──► www.memorysparkplay.fun ──┐                  │
│  API   ──► api.memorysparkplay.fun ──┤  Cloudflare      │
│  Ops   ──► ops.memorysparkplay.fun ──┤  Tunnel          │
│                                      ▼                  │
│                              ┌──────────────┐           │
│                              │ cloudflared  │           │
│                              │ (host svc)   │           │
│                              └──────┬───────┘           │
│                                     │ :8080             │
│  ┌──────────────────────────────────┼──────────────┐    │
│  │  Docker Host (VM)                │              │    │
│  │                                  ▼              │    │
│  │  ┌────────────────────────────────────────┐     │    │
│  │  │  mss-web container                     │     │    │
│  │  │  ┌─────────────┐  ┌────────────────┐   │     │    │
│  │  │  │  Gunicorn    │  │  Flask App     │   │     │    │
│  │  │  │  (2 workers) │──│  /api/*        │   │     │    │
│  │  │  │  :8080       │  │  /ops/*        │   │     │    │
│  │  │  └─────────────┘  └────────────────┘   │     │    │
│  │  │                                        │     │    │
│  │  │  Volumes:                              │     │    │
│  │  │    /data    ← cloud-data/data/         │     │    │
│  │  │    /sounds  ← cloud-data/Sounds/       │     │    │
│  │  │    /app/log ← cloud-data/log/          │     │    │
│  │  └────────────────────────────────────────┘     │    │
│  │                                                 │    │
│  │  SQLite: cloud-data/data/sound_machine.db       │    │
│  │  Audio:  cloud-data/Sounds/uploads/*.wav        │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Key Paths

| What               | Host Path                                      | Container Path         |
|--------------------|------------------------------------------------|------------------------|
| Database           | `cloud-data/data/sound_machine.db`             | `/data/sound_machine.db` |
| Audio files        | `cloud-data/Sounds/uploads/`                   | `/sounds/uploads/`     |
| App logs           | `cloud-data/log/`                              | `/app/log/`            |
| Docker Compose     | `docker-compose.yml`                           | —                      |
| Cloudflared config | `/etc/cloudflared/config.yml`                  | (mounted read-only)    |
| Repo root          | `~/Projects/sound-machine/`                    | `/app`                 |

## Common Symptoms → Checks → Fixes

### 503 Service Unavailable

**Meaning:** Cloudflare tunnel can't reach the backend.

**Checks:**
```bash
# Is the container running?
docker ps | grep mss-web

# Is the app responding?
curl -s http://localhost:8080/api/server-info

# Is cloudflared running?
sudo systemctl status cloudflared

# Check cloudflared logs
sudo journalctl -u cloudflared -n 50 --no-pager
```

**Fixes:**
```bash
# Restart the container
cd ~/Projects/sound-machine
docker compose restart web

# If container won't start, check logs
docker logs mss-web --tail 50

# Restart cloudflared
sudo systemctl restart cloudflared
```

### 404 on Trackpack Download

**Meaning:** Trackpack profile exists but zip generation failed or profile ID is wrong.

**Checks:**
```bash
# List published trackpacks
curl -s http://localhost:8080/api/trackpacks | python3 -m json.tool

# Try specific trackpack manifest
curl -s http://localhost:8080/api/trackpacks/1/manifest.json

# Check if audio files exist
ls -la cloud-data/Sounds/uploads/

# Check DB
sqlite3 cloud-data/data/sound_machine.db "SELECT id, name, published FROM profiles;"
```

**Fixes:**
- If audio files are missing, re-upload via the web UI
- If profile isn't published: `sqlite3 cloud-data/data/sound_machine.db "UPDATE profiles SET published=1 WHERE id=N;"`

### App Loads but Trackpacks Fail

**Meaning:** Web UI works but `/api/trackpacks` returns errors.

**Checks:**
```bash
# Check API directly
curl -s http://localhost:8080/api/trackpacks

# Check DB integrity
sqlite3 cloud-data/data/sound_machine.db "PRAGMA integrity_check;"

# Check for orphaned mappings
sqlite3 cloud-data/data/sound_machine.db \
  "SELECT bm.* FROM button_mappings bm LEFT JOIN audio_files af ON bm.audio_file_id=af.id WHERE af.id IS NULL;"
```

**Fixes:**
```bash
# Remove orphaned button mappings
sqlite3 cloud-data/data/sound_machine.db \
  "DELETE FROM button_mappings WHERE audio_file_id NOT IN (SELECT id FROM audio_files);"
```

### Tunnel Down (site completely unreachable)

**Checks:**
```bash
# Check cloudflared service
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -n 100 --no-pager

# Check if tunnel config is valid
sudo cat /etc/cloudflared/config.yml

# Check DNS
dig api.memorysparkplay.fun
dig www.memorysparkplay.fun
```

**Fixes:**
```bash
# Restart cloudflared
sudo systemctl restart cloudflared

# If config is corrupted, you'll need to re-configure the tunnel
# via the Cloudflare Zero Trust dashboard
```

### Database Missing or Corrupted

**Checks:**
```bash
# Check if DB exists
ls -la cloud-data/data/sound_machine.db

# Check integrity
sqlite3 cloud-data/data/sound_machine.db "PRAGMA integrity_check;"

# Check tables
sqlite3 cloud-data/data/sound_machine.db ".tables"
```

**Fixes:**
```bash
# If missing, initialize fresh DB
docker exec mss-web python -m db.init_db

# If corrupted, restore from backup (if available)
# Or reinitialize and re-import trackpacks
```

## Log Locations

| Source       | How to Access                                           |
|--------------|---------------------------------------------------------|
| Web app      | `docker logs mss-web --tail 200`                        |
| Cloudflared  | `sudo journalctl -u cloudflared -n 200 --no-pager`     |
| Gunicorn     | `cat cloud-data/log/gunicorn.log` (if configured)       |
| Health check | `journalctl -u mss-health --no-pager` (if timer active) |

## Safe Restart Procedures

### Restart web app only (no downtime for tunnel)
```bash
cd ~/Projects/sound-machine
docker compose restart web
```

### Full rebuild (after code changes)
```bash
cd ~/Projects/sound-machine
docker compose build web
docker compose up -d web
```

### Restart cloudflared
```bash
sudo systemctl restart cloudflared
```

### Full system restart
```bash
cd ~/Projects/sound-machine
docker compose down
sudo systemctl restart cloudflared
docker compose up -d
```

## Health Check

Run the automated health check:
```bash
./scripts/healthcheck.sh
```

To install as a recurring timer:
```bash
sudo cp scripts/mss-health.service /etc/systemd/system/
sudo cp scripts/mss-health.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mss-health.timer
# Check results:
journalctl -u mss-health --no-pager -n 20
```

## Ops Dashboard

Access at `https://ops.memorysparkplay.fun/ops` (or `http://localhost:8080/ops`).

Requires:
- `MSS_OPS_ENABLED=1` in environment
- `MSS_OPS_TOKEN` set to a shared secret
- Token entered in the dashboard UI

Generate a snapshot archive:
```bash
./scripts/ops_snapshot.sh /tmp/
```
