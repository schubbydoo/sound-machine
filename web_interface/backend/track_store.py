"""Storage for the shared Media tab (propkit.files): the station's tracks.

A track is a WAV in Sounds/ plus a row in audio_files; buttons point at the row's id, so renaming a file or replacing it
with a new upload keeps every button assignment. Uploads are converted to the playback format first (same rules as the old
upload form). Deleting removes the file, its row and its button assignments (the page warns first, see usage in app.py).
"""
import os
import wave
from pathlib import Path


class TrackStore:
    def __init__(self, get_db, sounds_root, needs_conversion, convert_wav):
        self.get_db = get_db
        self.sounds_root = Path(sounds_root)
        self.upload_dir = self.sounds_root / "uploads"
        self.root = str(self.sounds_root)                 # propkit checks free disk space here
        self.needs_conversion = needs_conversion
        self.convert_wav = convert_wav

    # -- helpers
    def _row(self, conn, name):
        return conn.execute("SELECT * FROM audio_files WHERE filename = ? ORDER BY id LIMIT 1", (name,)).fetchone()

    def _inside(self, p):
        real = os.path.realpath(p)
        root = os.path.realpath(self.sounds_root)
        return real.startswith(root + os.sep) and not os.path.islink(p)

    def path(self, name, collection=None):
        conn = self.get_db()
        try:
            row = self._row(conn, name)
        finally:
            conn.close()
        if not row or not self._inside(row["filepath"]):
            raise ValueError("bad name")
        return row["filepath"]

    def _seconds(self, p):
        try:
            with wave.open(p, "rb") as w:
                return round(w.getnframes() / float(w.getframerate()), 1)
        except Exception:
            return None

    # -- reading
    def collections(self):
        return []

    def list(self, collection=None):
        self._sync()
        out = []
        conn = self.get_db()
        try:
            for r in conn.execute("SELECT * FROM audio_files ORDER BY filename COLLATE NOCASE").fetchall():
                p = r["filepath"]
                if not os.path.isfile(p) or not self._inside(p):
                    continue
                st = os.stat(p)
                facts = [[k, r[col]] for k, col in (("Category", "category"), ("Hint", "hint")) if r[col]]
                out.append({"id": r["filename"], "name": r["filename"], "size": st.st_size, "mtime": int(st.st_mtime),
                            "description": r["description"] or "", "seconds": self._seconds(p),
                            "extra": {}, "facts": facts})
        finally:
            conn.close()
        return out

    def _sync(self):
        """Files that appeared on disk (cloud packs, copied in by hand) get their row, like the Tracks page always did."""
        try:
            conn = self.get_db()
            try:
                known = {r["filepath"] for r in conn.execute("SELECT filepath FROM audio_files").fetchall()}
                for p in self.sounds_root.rglob("*.wav"):
                    if p.name.startswith("."):                       # an upload still being written
                        continue
                    rp = str(p.resolve())
                    if rp not in known:
                        conn.execute("INSERT INTO audio_files (filename, filepath) VALUES (?, ?)", (p.name, rp))
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def description(self, name, collection=None):
        conn = self.get_db()
        try:
            r = self._row(conn, name)
            return (r["description"] or "") if r else ""
        finally:
            conn.close()

    def usage_bytes(self):
        total = 0
        for dirpath, dirs, files in os.walk(self.sounds_root):
            total += sum(os.path.getsize(os.path.join(dirpath, f)) for f in files if f.lower().endswith(".wav"))
        return total

    # -- writing (propkit has already checked the content, size and disk space)
    def save(self, tmp_path, name, collection=None, on_duplicate="ask"):
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        conn = self.get_db()
        try:
            exists = self._row(conn, name) is not None or (self.upload_dir / name).exists()
            status = "saved"
            if exists:
                if on_duplicate == "skip":
                    return {"status": "skipped", "name": name}
                if on_duplicate == "replace":
                    status = "replaced"
                elif on_duplicate == "keep_both":
                    base, ext = os.path.splitext(name)
                    n = 2
                    while self._row(conn, "%s (%d)%s" % (base, n, ext)) or (self.upload_dir / ("%s (%d)%s" % (base, n, ext))).exists():
                        n += 1
                    name = "%s (%d)%s" % (base, n, ext)
                    status = "kept_both"
                else:
                    return {"status": "exists", "name": name}
            dest = self.upload_dir / name
            part = dest.with_name("." + dest.stem + ".part.wav")           # finish the whole file before it can be played
            try:
                if self.needs_conversion(tmp_path):
                    try:
                        self.convert_wav(tmp_path, part)
                    except Exception:
                        raise OSError(5, "this sound could not be converted to the playback format")
                else:
                    os.replace(tmp_path, part)
                os.chmod(str(part), 0o644)
                os.replace(part, dest)
            finally:
                for leftover in (part,):
                    if leftover.exists():
                        leftover.unlink()
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            if not self._row(conn, name):
                conn.execute("INSERT INTO audio_files (filename, filepath) VALUES (?, ?)", (name, str(dest.resolve())))
                conn.commit()
            return {"status": status, "name": name}
        finally:
            conn.close()

    def delete(self, name, collection=None):
        conn = self.get_db()
        try:
            row = self._row(conn, name)
            if not row:
                raise FileNotFoundError(name)
            if self._inside(row["filepath"]) and os.path.exists(row["filepath"]):
                os.remove(row["filepath"])
            conn.execute("DELETE FROM button_mappings WHERE audio_file_id = ?", (row["id"],))
            conn.execute("DELETE FROM audio_files WHERE id = ?", (row["id"],))
            conn.commit()
        finally:
            conn.close()

    def rename(self, name, new, collection=None):
        conn = self.get_db()
        try:
            row = self._row(conn, name)
            if not row:
                raise FileNotFoundError(name)
            dst = Path(row["filepath"]).with_name(new)
            if dst.exists() or self._row(conn, new):
                raise FileExistsError(new)
            os.rename(row["filepath"], dst)
            conn.execute("UPDATE audio_files SET filename = ?, filepath = ? WHERE id = ?", (new, str(dst.resolve()), row["id"]))
            conn.commit()
        finally:
            conn.close()

    def describe(self, name, text, collection=None):
        conn = self.get_db()
        try:
            if not self._row(conn, name):
                raise ValueError("bad name")
            conn.execute("UPDATE audio_files SET description = ? WHERE filename = ?", (text, name))
            conn.commit()
        finally:
            conn.close()
