"""Database initialization for MSS backend.

Creates the SQLite database with required schema if it doesn't exist.

Usage:
    # Using environment variable:
    MSS_DB_PATH=/path/to/db.sqlite python db/init_db.py

    # Using command line argument:
    python db/init_db.py --db-path /path/to/db.sqlite

    # Using defaults (auto-detect project root):
    python db/init_db.py
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path


# Legacy Pi deployment path (backward compatibility)
_LEGACY_PI_ROOT = Path('/home/soundconsole/sound-machine')


def _detect_project_root() -> Path:
    """Detect project root by walking up from this file."""
    # This file: {project_root}/db/init_db.py
    init_db_file = Path(__file__).resolve()
    db_dir = init_db_file.parent        # db/
    project_root = db_dir.parent        # project root
    return project_root


def _get_default_db_path() -> Path:
    """Determine default database path using same logic as config.py.

    Priority:
    1. MSS_DB_PATH environment variable
    2. MSS_DATA_DIR/sound_machine.db if MSS_DATA_DIR is set
    3. MSS_ROOT/data/sound_machine.db if MSS_ROOT is set
    4. Auto-detected project root
    5. Legacy Pi path as fallback
    """
    # Direct DB path override
    env_db = os.environ.get('MSS_DB_PATH')
    if env_db:
        return Path(env_db)

    # Data dir override
    env_data = os.environ.get('MSS_DATA_DIR')
    if env_data:
        return Path(env_data) / 'sound_machine.db'

    # Root override
    env_root = os.environ.get('MSS_ROOT')
    if env_root:
        return Path(env_root) / 'data' / 'sound_machine.db'

    # Auto-detect from file location
    detected = _detect_project_root()
    if (detected / 'web_interface').exists():
        return detected / 'data' / 'sound_machine.db'

    # Legacy Pi path if it exists
    if _LEGACY_PI_ROOT.exists():
        return _LEGACY_PI_ROOT / 'data' / 'sound_machine.db'

    # Final fallback to detected path
    return detected / 'data' / 'sound_machine.db'


SCHEMA_SQL = """
-- Enable foreign key support
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    instructions TEXT,
    published INTEGER NOT NULL DEFAULT 0,
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
    profile_id INTEGER,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL
);

-- Config table for system-wide settings
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_db(db_path: Path = None) -> Path:
    """Initialize the database at the given path.

    Creates the parent directory if needed, then creates/updates the schema.

    Args:
        db_path: Path to the database file. If None, uses default detection.

    Returns:
        The path to the initialized database.
    """
    if db_path is None:
        db_path = _get_default_db_path()

    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Execute schema
    cursor.executescript(SCHEMA_SQL)

    # Seed initial system config if empty
    cursor.execute(
        "INSERT OR IGNORE INTO system_config (key, value) VALUES (?, ?)",
        ("active_channel", "1")
    )

    conn.commit()
    conn.close()
    print(f"Database initialized at {db_path}")

    return db_path


def main():
    """CLI entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Initialize the MSS SQLite database'
    )
    parser.add_argument(
        '--db-path',
        type=Path,
        default=None,
        help='Path to database file (default: auto-detect or use MSS_DB_PATH env var)'
    )
    args = parser.parse_args()

    init_db(args.db_path)


if __name__ == "__main__":
    main()
