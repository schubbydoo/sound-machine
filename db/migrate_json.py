import json
import sqlite3
import os
from pathlib import Path

# Paths
BASE_DIR = Path('/home/soundconsole/sound-machine')
JSON_CONFIG_PATH = BASE_DIR / 'config' / 'mappings.json'
DB_PATH = BASE_DIR / 'data' / 'sound_machine.db'

def migrate():
    if not JSON_CONFIG_PATH.exists():
        print(f"No mappings.json found at {JSON_CONFIG_PATH}, skipping migration.")
        return

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run init_db.py first.")
        return

    print(f"Migrating data from {JSON_CONFIG_PATH}...")
    
    with open(JSON_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    profiles = config.get('profiles', {})
    channel_idx = 1

    for profile_name, profile_data in profiles.items():
        print(f"Processing profile: {profile_name}")
        
        # 1. Insert Profile
        cursor.execute("INSERT OR IGNORE INTO profiles (name) VALUES (?)", (profile_name,))
        cursor.execute("SELECT id FROM profiles WHERE name = ?", (profile_name,))
        profile_id = cursor.fetchone()[0]
        
        base_dir = Path(profile_data.get('baseDir', ''))
        # If baseDir is relative, make it absolute based on BASE_DIR/Sounds if possible, 
        # but mappings.json usually has absolute paths or paths relative to some root.
        # existing code uses: (base_dir / rel).resolve()
        
        buttons = profile_data.get('buttons', {})
        
        for btn_key, filename in buttons.items():
            if not filename:
                continue
            
            try:
                button_id = int(btn_key)
            except ValueError:
                continue
                
            # Construct full path
            full_path = (base_dir / filename).resolve()
            str_path = str(full_path)
            
            # 2. Insert Audio File
            # We assume filename is the name, and filepath is the unique path
            # Check if file exists in DB
            cursor.execute("SELECT id FROM audio_files WHERE filepath = ?", (str_path,))
            row = cursor.fetchone()
            
            if row:
                audio_file_id = row[0]
            else:
                cursor.execute(
                    "INSERT INTO audio_files (filename, filepath) VALUES (?, ?)", 
                    (filename, str_path)
                )
                audio_file_id = cursor.lastrowid
            
            # 3. Insert Button Mapping
            cursor.execute(
                """
                INSERT OR REPLACE INTO button_mappings (profile_id, button_id, audio_file_id)
                VALUES (?, ?, ?)
                """,
                (profile_id, button_id, audio_file_id)
            )

        # 4. Assign to a channel (Just sequential 1-4 for now)
        if channel_idx <= 4:
            cursor.execute(
                "INSERT OR REPLACE INTO channels (channel_number, profile_id) VALUES (?, ?)",
                (channel_idx, profile_id)
            )
            print(f"  Assigned to Channel {channel_idx}")
            channel_idx += 1

    # 5. Migrate Device Config
    device_cfg = config.get('device', {})
    for key, value in device_cfg.items():
        if isinstance(value, (str, int, float)):
            cursor.execute(
                "INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            print(f"  Migrated device setting: {key}={value}")
    
    # 6. Ensure active_channel is set (default to 1 if not present)
    cursor.execute("INSERT OR IGNORE INTO system_config (key, value) VALUES (?, ?)", ("active_channel", "1"))
            
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()

