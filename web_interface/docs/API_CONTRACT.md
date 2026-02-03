# MSS Backend API Contract

This document describes the public HTTP API for the Memory Spark Station (MSS) backend.

## Base URL

- Local: `http://soundconsole.local:8080`
- Direct IP: `http://<pi-ip>:8080`

---

## Server Identity

### GET /api/server-info

Returns server identification and capabilities. The `server_id` is persistent
across restarts and reboots, making it suitable for client pairing and sync.

**Response:**

```json
{
  "ok": true,
  "server_id": "mss-local-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "server_name": "Memory Spark Station",
  "server_type": "local",
  "api_version": "v1",
  "capabilities": {
    "trackpacks": true,
    "updates": true,
    "cloud_ready": true
  }
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true` on success |
| `server_id` | string | Stable unique identifier for this MSS instance. Format: `mss-local-<uuid4>`. Persisted to disk, survives restarts. |
| `server_name` | string | Human-friendly display name. Defaults to "Memory Spark Station". Can be customized via `/home/soundconsole/sound-machine/data/server_name.txt`. |
| `server_type` | string | Deployment type. Currently always `"local"`. Future: `"cloud"`. |
| `api_version` | string | API version identifier. Currently `"v1"`. |
| `capabilities` | object | Feature flags indicating what this server supports. |

**Capabilities:**

| Capability | Type | Description |
|------------|------|-------------|
| `trackpacks` | boolean | Server can serve trackpack listings, manifests, and ZIPs |
| `updates` | boolean | Server supports revision-based update detection |
| `cloud_ready` | boolean | Server has cloud-compatible abstractions in place |

---

## Trackpacks

### GET /api/trackpacks

Lists all available trackpacks with versioning metadata.

**Response:**

```json
{
  "ok": true,
  "trackpacks": [
    {
      "id": 5,
      "name": "70-80s Music",
      "instructions": "Name the song and the artist.",
      "stable_id": "trackpack-5",
      "revision": "609bb6f6800b967d",
      "updated_at": "2026-02-02T09:25:00Z"
    }
  ]
}
```

**Fields per trackpack:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Database ID (used in URLs) |
| `name` | string | Human-readable display name |
| `instructions` | string | Instructions shown to users |
| `stable_id` | string | Immutable identifier: `trackpack-<id>` |
| `revision` | string | 16-char hex hash of content. Changes when audio/metadata changes. |
| `updated_at` | string | ISO 8601 UTC timestamp of last content change |

---

### GET /api/trackpacks/\<id\>/manifest.json

Returns the manifest for a single trackpack.

**Response:**

```json
{
  "format": "mss-trackpack",
  "version": 1,
  "stable_id": "trackpack-5",
  "revision": "609bb6f6800b967d",
  "track": {
    "id": 5,
    "name": "70-80s Music",
    "instructions": "Name the song and the artist."
  },
  "buttons": [
    {
      "button": 1,
      "filename": "song.wav",
      "answer": "Artist - Song Title",
      "hint": "80s rock band",
      "category": "rock"
    }
  ]
}
```

---

### GET /api/trackpacks/\<id\>.zip

Downloads the trackpack as a ZIP file.

**Response:** Binary ZIP file

**ZIP Contents:**
```
manifest.json
audio/
  ├── song1.wav
  ├── song2.wav
  └── ...
```

**Caching:** ZIPs are cached on disk by revision. Filename format: `{stable_id}_{revision}.zip`

**Headers:**
- `Content-Type: application/zip`
- `Content-Disposition: attachment; filename="<name>.zip"`

---

## Revision System

The `revision` field is a content-based hash (SHA256, truncated to 16 hex chars).

**Revision changes when:**
- Track name or instructions change
- Button mappings change (add/remove/reorder)
- Audio file content changes (detected via mtime + size)
- Answer, hint, or category fields change

**Revision does NOT change when:**
- Server restarts
- Unrelated files are modified

**Client usage:**
1. Fetch `/api/trackpacks` to get current revisions
2. Compare against locally cached revisions
3. Re-download ZIP only if revision differs

---

## Timestamps

The `updated_at` field uses ISO 8601 UTC format: `YYYY-MM-DDTHH:MM:SSZ`

**Priority for determining updated_at:**
1. Database `updated_at` column (if present and valid)
2. Maximum `mtime` of all audio files in the trackpack
3. Database `created_at` column (if present and valid)
4. Current time (last resort)

This ensures `updated_at` reflects actual content changes even on older database schemas.
