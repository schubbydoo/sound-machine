import os
import subprocess
import sqlite3
import shutil
from pathlib import Path

# Configuration
SOUNDS_DIR = Path('/home/soundconsole/sound-machine/Sounds')
DB_PATH = Path('/home/soundconsole/sound-machine/data/sound_machine.db')
TARGET_RATE = 44100

def get_wav_info(path):
    try:
        cmd = ['soxi', str(path)]
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        return output
    except:
        return ""

def convert_to_44100(path):
    tmp_path = path.with_suffix('.tmp.wav')
    print(f"Converting {path.name} to 44.1kHz...")
    try:
        # Use ffmpeg for conversion
        cmd = [
            'ffmpeg', '-y', '-v', 'error',
            '-i', str(path),
            '-ar', str(TARGET_RATE),
            '-acodec', 'pcm_s16le',
            str(tmp_path)
        ]
        subprocess.check_call(cmd)
        shutil.move(str(tmp_path), str(path))
        print("  Success")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False

def fix_duplicates_and_format():
    # 1. Convert all files to 44.1kHz
    for wav_file in SOUNDS_DIR.rglob('*.wav'):
        # Check sample rate (simple grep or always convert to be safe)
        # "soxi" might not be installed, ffmpeg probe is verbose.
        # Let's just re-run conversion if we suspect it's wrong, 
        # but to save time, maybe check file size or just do it.
        # Given the "static" issue, strict 44.1k is needed.
        convert_to_44100(wav_file)

    # 2. Handle duplicates (cleanup uploads)
    # Strategy: 
    # - Find files with timestamp patterns (e.g., _20251125_202044.wav)
    # - Find the "base" file (without timestamp)
    # - If base exists, update DB to point to base, delete timestamped one.
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    uploads_dir = SOUNDS_DIR / 'uploads'
    if uploads_dir.exists():
        for f in uploads_dir.glob('*_????????_??????.wav'):
            # Check if it looks like a timestamped dupe
            # Pattern: Name_YYYYMMDD_HHMMSS.wav
            name = f.name
            try:
                # Split off the last 2 parts separated by underscore
                parts = name.rsplit('_', 2)
                if len(parts) >= 3:
                    base_name = parts[0] + f.suffix # Reconstruct original name? 
                    # Actually parts[0] might contain underscores.
                    # safer: stem minus last 16 chars? 
                    # _20251125_202044 is 16 chars.
                    
                    original_name = name[:-20] + ".wav" # _YYYYMMDD_HHMMSS is 16 chars + .wav (4) = 20? 
                    # _20251125_202044 is 1 + 8 + 1 + 6 = 16. 
                    # ".wav" is 4. Total 20.
                    
                    original_file = uploads_dir / original_name
                    
                    if original_file.exists():
                        print(f"Found duplicate: {f.name} -> {original_name}")
                        
                        # 1. Update DB to point to original_file
                        # Find ID of the duplicate
                        cursor.execute("SELECT id FROM audio_files WHERE filepath = ?", (str(f.resolve()),))
                        dupe_row = cursor.fetchone()
                        
                        cursor.execute("SELECT id FROM audio_files WHERE filepath = ?", (str(original_file.resolve()),))
                        orig_row = cursor.fetchone()
                        
                        if dupe_row and orig_row:
                            dupe_id = dupe_row['id']
                            orig_id = orig_row['id']
                            
                            print(f"  Remapping DB: {dupe_id} -> {orig_id}")
                            cursor.execute("UPDATE button_mappings SET audio_file_id = ? WHERE audio_file_id = ?", (orig_id, dupe_id))
                            cursor.execute("DELETE FROM audio_files WHERE id = ?", (dupe_id,))
                            
                            # Delete the file
                            print("  Deleting duplicate file")
                            f.unlink()
                            
                        elif dupe_row and not orig_row:
                            # Original file exists on disk but not in DB? Weird.
                            # Just update the dupe row to point to original file path
                            print("  Updating DB path to original file")
                            cursor.execute("UPDATE audio_files SET filepath = ?, filename = ? WHERE id = ?", 
                                           (str(original_file.resolve()), original_name, dupe_row['id']))
                            f.unlink()
            except Exception as e:
                print(f"Error handling duplicate {f.name}: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    fix_duplicates_and_format()









