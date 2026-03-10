#!/usr/bin/env python3
"""
Library migration — adds playlist management columns to profiles table.
Safe to run multiple times (idempotent).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path('/home/soundconsole/sound-machine/data/sound_machine.db')


def migrate():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        # Add columns (each wrapped separately so partial failures don't block others)
        new_columns = [
            ("in_playlist",     "INTEGER DEFAULT 0"),
            ("playlist_order",  "INTEGER"),
            ("source",          "TEXT DEFAULT 'local'"),
            ("cloud_stable_id", "TEXT"),
            ("cloud_revision",  "TEXT"),
        ]
        for col, typedef in new_columns:
            try:
                conn.execute(f"ALTER TABLE profiles ADD COLUMN {col} {typedef}")
                print(f"  + Added column: {col}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print(f"  ~ Column already exists: {col}")
                else:
                    raise

        conn.commit()

        # Seed playlist from current channel assignments
        # Channel 1→profile 13, 2→5, 3→8, 4→6
        channels = conn.execute(
            "SELECT channel_number, profile_id FROM channels ORDER BY channel_number"
        ).fetchall()

        if channels:
            print(f"\nSeeding playlist from {len(channels)} channel assignments:")
            for ch in channels:
                order = ch['channel_number']
                pid   = ch['profile_id']
                name  = conn.execute(
                    "SELECT name FROM profiles WHERE id=?", (pid,)
                ).fetchone()
                label = name['name'] if name else f"id={pid}"
                conn.execute(
                    "UPDATE profiles SET in_playlist=1, playlist_order=? WHERE id=?",
                    (order, pid)
                )
                print(f"  Track {order}: {label} (profile_id={pid})")
            conn.commit()
        else:
            print("  No channel assignments found — playlist starts empty.")

        # Determine initial active_profile_id from current active_channel
        row = conn.execute(
            "SELECT value FROM system_config WHERE key='active_channel'"
        ).fetchone()
        active_channel = int(row['value']) if row else 1

        ch_row = conn.execute(
            "SELECT profile_id FROM channels WHERE channel_number=?", (active_channel,)
        ).fetchone()

        if ch_row:
            active_profile_id = ch_row['profile_id']
            conn.execute(
                "INSERT OR REPLACE INTO system_config (key, value) VALUES ('active_profile_id', ?)",
                (str(active_profile_id),)
            )
            print(f"\nSet active_profile_id = {active_profile_id} "
                  f"(from active_channel={active_channel})")
        else:
            # Fall back to first playlist entry
            first = conn.execute(
                "SELECT id FROM profiles WHERE in_playlist=1 ORDER BY playlist_order LIMIT 1"
            ).fetchone()
            if first:
                conn.execute(
                    "INSERT OR REPLACE INTO system_config (key, value) VALUES ('active_profile_id', ?)",
                    (str(first['id']),)
                )
                print(f"\nSet active_profile_id = {first['id']} (first playlist entry)")

        conn.commit()
        print("\nMigration complete.")

    finally:
        conn.close()


if __name__ == '__main__':
    print(f"Migrating: {DB_PATH}\n")
    migrate()
