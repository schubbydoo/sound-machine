# Memory Spark Station – API Contract (Canonical)

Status: Stable (v1)
Audience: MSS Backend, Mobile App, Future Cloud Service

This document is the single source of truth for how trackpacks are identified,
versioned, updated, and delivered. Both the MSS backend and the mobile app must
conform to this contract. Any change that violates this document is a breaking
change and must be versioned deliberately.

────────────────────────────────────────────────────────────

## 1. Core Concepts

### 1.1 Trackpack

A Trackpack is a complete, self-contained unit consisting of:
- Track metadata (name, instructions)
- Button mappings (button → audio file)
- Optional hints, answers, and categories
- Audio files
- A computed revision hash

A Trackpack is immutable for a given revision.

---

### 1.2 Stable ID

Each Trackpack has a stable identifier that never changes.

Format:
trackpack-{numeric_id}

Examples:
- trackpack-1
- trackpack-13

Rules:
- stable_id uniquely identifies a Trackpack across all environments
- Display names are NOT guaranteed to be unique
- Clients must never rely on name for identity

---

### 1.3 Revision

Each Trackpack has a revision string.

Properties:
- Content-addressed fingerprint
- Changes whenever ANY trackpack content changes

Revision MUST change if any of the following change:
- Track name or instructions
- Button mappings (add, remove, reorder)
- Hint, answer, or category values
- Audio file content
- Audio file metadata (mtime or size)

Guarantees:
- Different revision means different content
- Same revision means identical content

---

### 1.4 updated_at

Each Trackpack exposes an updated_at timestamp (ISO 8601 UTC).

Priority order:
1. Database updated_at (if present and valid)
2. Maximum mtime of all audio files
3. Database created_at (if present and valid)
4. Current server time (last resort)

Guarantees:
- updated_at always exists
- updated_at reflects the most recent meaningful content change

────────────────────────────────────────────────────────────

## 2. API Endpoints

### 2.1 List Trackpacks

GET /api/trackpacks

Response shape:
{
  "ok": true,
  "trackpacks": [
    {
      "id": 13,
      "stable_id": "trackpack-13",
      "name": "Movie Villains",
      "instructions": "Name the movie, character, or actor who plays the villain.",
      "revision": "9d424eae964abaf3",
      "updated_at": "2026-02-02T17:52:13Z"
    }
  ]
}

Guarantees:
- stable_id, revision, and updated_at are always present
- Order is not guaranteed
- Duplicate names are allowed

---

### 2.2 Trackpack Manifest

GET /api/trackpacks/{id}/manifest.json

Behavior:
- Returns full manifest metadata
- Includes stable_id, revision, updated_at
- Contains full button mappings
- Does NOT include audio bytes

Manifest revision MUST match ZIP revision.

---

### 2.3 Trackpack ZIP Download

GET /api/trackpacks/{id}.zip

Behavior:
- ZIP filename includes revision
- ZIP contains:
  - manifest.json
  - audio/ directory with all referenced audio files
- ZIPs are generated atomically
- Old ZIP revisions are cleaned up automatically

Guarantees:
- ZIP revision equals manifest revision
- ZIP contents are immutable per revision

────────────────────────────────────────────────────────────

## 3. Mobile App Responsibilities

- Use stable_id for identity
- Never rely on name uniqueness
- Detect updates by comparing revisions
- Store one local copy per stable_id
- Re-download the entire ZIP when revision changes
- Remain functional offline using cached content
- Network errors must never crash the app

────────────────────────────────────────────────────────────

## 4. Backend Responsibilities (MSS / Cloud)

- Revision computation must be deterministic and conservative
- Same content must always produce the same revision
- ZIP generation must be atomic
- All file access must go through a storage adapter
- No direct filesystem assumptions in core logic

────────────────────────────────────────────────────────────

## 5. Cloud Compatibility Requirements

A cloud backend must:
- Preserve stable_id semantics
- Preserve revision semantics
- Preserve updated_at rules
- Serve identical API responses
- Serve immutable, revision-addressed ZIPs

The mobile app must not require changes when switching from
local MSS to cloud MSS, aside from base URL configuration.

────────────────────────────────────────────────────────────

## 6. Versioning Policy

This document defines API v1.

Breaking changes require:
- A new API version
- Parallel support during migration
- An explicit mobile app upgrade path

Non-breaking changes:
- New optional fields
- Additional endpoints

────────────────────────────────────────────────────────────

End of document.
