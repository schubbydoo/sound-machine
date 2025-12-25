import sqlite3
from pathlib import Path

DB_PATH = Path('/home/soundconsole/sound-machine/data/sound_machine.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
    if not cursor.fetchone():
        print("Table 'channels' does not exist. Skipping migration.")
        return

    print("Starting migration to remove UNIQUE constraint from channels.profile_id...")

    try:
        conn.execute("BEGIN TRANSACTION")

        # 1. Rename old table
        conn.execute("ALTER TABLE channels RENAME TO channels_old")

        # 2. Create new table without UNIQUE on profile_id
        conn.execute("""
            CREATE TABLE channels (
                channel_number INTEGER PRIMARY KEY CHECK(channel_number >= 1 AND channel_number <= 4),
                profile_id INTEGER,
                FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL
            )
        """)

        # 3. Copy data
        conn.execute("INSERT INTO channels (channel_number, profile_id) SELECT channel_number, profile_id FROM channels_old")

        # 4. Drop old table
        conn.execute("DROP TABLE channels_old")

        conn.commit()
        print("Migration successful.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()





