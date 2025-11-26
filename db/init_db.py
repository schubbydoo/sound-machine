import sqlite3
import os
from pathlib import Path

DB_PATH = Path('/home/soundconsole/sound-machine/data/sound_machine.db')
SCHEMA_SQL = """
-- Enable foreign key support
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audio_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT UNIQUE NOT NULL,
    description TEXT,
    category TEXT,
    tags TEXT,
    hint TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS button_mappings (
    profile_id INTEGER,
    button_id INTEGER CHECK(button_id >= 1 AND button_id <= 16),
    audio_file_id INTEGER,
    PRIMARY KEY (profile_id, button_id),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (audio_file_id) REFERENCES audio_files(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS channels (
    channel_number INTEGER PRIMARY KEY CHECK(channel_number >= 1 AND channel_number <= 4),
    profile_id INTEGER UNIQUE, -- Prevent same profile on multiple channels if desired, though requirements say "Conflicts should be gracefully handled"
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL
);

-- Config table for system-wide settings
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

def init_db():
    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Execute schema
    cursor.executescript(SCHEMA_SQL)
    
    # Seed initial system config if empty
    cursor.execute("INSERT OR IGNORE INTO system_config (key, value) VALUES (?, ?)", ("active_channel", "1"))
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()

