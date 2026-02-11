# MSS Backups

Backups protect your trackpacks, audio files, and database. They run
automatically every night and can also be triggered manually.

---

## What Gets Backed Up

| What | Where it lives | Why it matters |
|------|---------------|----------------|
| Database | `cloud-data/data/sound_machine.db` | All your trackpacks, button mappings, and metadata |
| Server identity | `cloud-data/data/server_id.txt` | How the mobile app recognizes this MSS instance |
| Trackpack exports | `cloud-data/data/exports/` | Pre-built zip files for download |
| Audio files | `cloud-data/Sounds/uploads/` | Every WAV file you've uploaded |
| Configuration | `cloud-data/config/` | WiFi and Bluetooth settings |
| Logs | `cloud-data/log/` | App activity logs |
| System snapshot | `inventory.txt` (inside the backup) | Docker status, git version, disk usage at backup time |

Each backup is a single compressed file (~388 MB).

---

## Where Backups Are Stored

```
~/backups/mss/
├── archive/
│   ├── mss-backup-2026-02-10_203350.tar.gz
│   ├── mss-backup-2026-02-11_031500.tar.gz
│   └── mss-backup-latest.tar.gz  →  (always points to newest)
├── last_backup.json    ←  status of the most recent backup
└── backup.log          ←  full history of all backup runs
```

The **last 7 backups** are kept. Older ones are automatically deleted.

---

## Automatic Backups

Backups run every night at **3:15 AM**. If the VM was off at that time,
the backup runs as soon as the VM starts again.

To check when the next backup will run:
```bash
systemctl --user list-timers mss-backup.timer
```

To see if the last automatic backup worked:
```bash
cat ~/backups/mss/last_backup.json | python3 -m json.tool
```

---

## How To: Run a Backup Right Now

```bash
~/Projects/sound-machine/scripts/mss-backup
```

This is safe to run at any time — it won't interrupt MSS or restart anything.
If a backup is already running, the second one will exit immediately.

---

## How To: Check Backup Status

**Quick status:**
```bash
cat ~/backups/mss/last_backup.json | python3 -m json.tool
```

Look for `"status": "success"`. If it says `"failure"`, check the log:
```bash
tail -50 ~/backups/mss/backup.log
```

**List all backups on disk:**
```bash
ls -lh ~/backups/mss/archive/
```

---

## How To: Restore Just the Database

Use this if trackpacks are missing or the database is corrupted, but your
audio files are fine.

```bash
# 1. Stop MSS
cd ~/Projects/sound-machine
docker compose down

# 2. Save current DB as a safety net
cp cloud-data/data/sound_machine.db cloud-data/data/sound_machine.db.broken

# 3. Extract only the DB from the latest backup
tar -xzf ~/backups/mss/archive/mss-backup-latest.tar.gz \
    -C cloud-data/ data/sound_machine.db

# 4. Start MSS again
docker compose up -d

# 5. Verify (wait a few seconds, then check)
sleep 5
curl http://localhost:8080/api/trackpacks | python3 -m json.tool
```

---

## How To: Restore Audio Files Only

Use this if audio files were accidentally deleted but the database is fine.

```bash
# 1. Stop MSS
cd ~/Projects/sound-machine
docker compose down

# 2. Extract only Sounds from the latest backup
tar -xzf ~/backups/mss/archive/mss-backup-latest.tar.gz \
    -C cloud-data/ Sounds/

# 3. Start MSS again
docker compose up -d
```

---

## How To: Full Restore (Everything)

Use this to roll back to a known-good state.

```bash
# 1. Stop MSS
cd ~/Projects/sound-machine
docker compose down

# 2. Save current state as a safety net
cp -a cloud-data cloud-data.pre-restore

# 3. Pick a backup (or use latest)
ls -lh ~/backups/mss/archive/
BACKUP=~/backups/mss/archive/mss-backup-latest.tar.gz

# 4. Extract into a temp directory first
mkdir -p /tmp/mss-restore
tar -xzf "$BACKUP" -C /tmp/mss-restore/

# 5. Copy restored files into place
cp -a /tmp/mss-restore/data/*    cloud-data/data/
cp -a /tmp/mss-restore/Sounds/*  cloud-data/Sounds/
cp -a /tmp/mss-restore/config/*  cloud-data/config/ 2>/dev/null || true
cp -a /tmp/mss-restore/log/*     cloud-data/log/    2>/dev/null || true

# 6. Start MSS again
docker compose up -d

# 7. Verify
sleep 5
curl http://localhost:8080/api/server-info
curl http://localhost:8080/api/trackpacks | python3 -m json.tool

# 8. Clean up
rm -rf /tmp/mss-restore
# After verifying everything works:
# rm -rf cloud-data.pre-restore
```

---

## How This Fits With VM Snapshots

| Backup type | What it covers | Best for |
|------------|---------------|----------|
| **MSS backup** (this system) | Database + audio + config | Recovering from data loss, rolling back trackpack changes |
| **VM snapshot** (your cloud provider) | Entire virtual machine | Disaster recovery, recovering from OS or Docker failures |

They complement each other:
- MSS backups are **granular** — you can restore just the DB or just audio
- VM snapshots are **complete** — they restore everything including Docker, system config, and the OS itself

For full protection, use both.

---

## Future: Pluggable Targets

Currently backups are stored locally on the VM. The script is designed to
support additional targets later:

| Target | What it does | When to use |
|--------|-------------|-------------|
| **USB drive** | Copies backup to a mounted USB stick | Physical offsite backup |
| **rsync** | Syncs to another server over SSH | Remote backup to a NAS or second VM |
| **S3** | Uploads to Amazon S3 or compatible storage | Cloud backup |

These are not active yet. When needed, they can be enabled by setting
environment variables — no code changes required.

---

## Troubleshooting

**"Another mss-backup is already running"**
A backup is in progress. Wait for it to finish, or check if a previous
run got stuck:
```bash
ps aux | grep mss-backup
```

**Backup fails with "Cloud data directory not found"**
The MSS data directory is missing or moved. Check that `cloud-data/`
exists in the project directory:
```bash
ls ~/Projects/sound-machine/cloud-data/
```

**Disk space running low**
Lower the retention count (default is 7):
```bash
MSS_BACKUP_RETENTION=3 ~/Projects/sound-machine/scripts/mss-backup
```

**Timer not running**
Check if it's enabled:
```bash
systemctl --user list-timers mss-backup.timer
```
If not listed, re-enable:
```bash
systemctl --user enable --now mss-backup.timer
```
