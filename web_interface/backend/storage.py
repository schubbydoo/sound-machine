"""Storage adapter abstraction for trackpack audio files.

This module provides a clean boundary between the MSS backend logic and
the underlying storage system. Today we use local filesystem; in the future
this can be swapped for cloud object storage (S3/GCS) with minimal changes.

Usage:
    from backend.storage import get_storage_adapter
    adapter = get_storage_adapter()

    # Get file metadata for hashing/timestamps
    meta = adapter.get_file_metadata(filepath)
    if meta:
        print(f"size={meta.size}, mtime={meta.mtime}")

    # Read file bytes for ZIP generation
    data = adapter.read_file_bytes(filepath)
"""

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class FileMetadata:
    """Metadata about a stored file, used for hashing and timestamps."""
    size: int          # File size in bytes
    mtime: float       # Modification time as Unix timestamp
    exists: bool = True


class StorageAdapter:
    """Abstract base for storage backends.

    All storage operations for trackpack audio files go through this interface.
    Implementations must provide consistent behavior regardless of where files
    actually live (local disk, S3, GCS, etc.).
    """

    def get_file_metadata(self, filepath: str) -> Optional[FileMetadata]:
        """Get metadata for a file without reading its contents.

        Args:
            filepath: Path/key to the file

        Returns:
            FileMetadata with size and mtime, or None if file doesn't exist
        """
        raise NotImplementedError

    def file_exists(self, filepath: str) -> bool:
        """Check if a file exists.

        Args:
            filepath: Path/key to the file

        Returns:
            True if file exists and is readable
        """
        raise NotImplementedError

    def read_file_bytes(self, filepath: str) -> Optional[bytes]:
        """Read entire file contents as bytes.

        Args:
            filepath: Path/key to the file

        Returns:
            File contents as bytes, or None if file doesn't exist
        """
        raise NotImplementedError

    def get_files_metadata(self, filepaths: List[str]) -> Dict[str, Optional[FileMetadata]]:
        """Get metadata for multiple files efficiently.

        Default implementation calls get_file_metadata() for each file.
        Cloud implementations may batch these calls for efficiency.

        Args:
            filepaths: List of paths/keys

        Returns:
            Dict mapping filepath to FileMetadata (or None if missing)
        """
        return {fp: self.get_file_metadata(fp) for fp in filepaths}


class LocalStorageAdapter(StorageAdapter):
    """Storage adapter for local filesystem (Pi deployment).

    This is the default adapter used when running on the physical MSS device.
    Audio files are stored directly on the local filesystem.
    """

    def get_file_metadata(self, filepath: str) -> Optional[FileMetadata]:
        """Get metadata from local filesystem stat()."""
        try:
            p = Path(filepath)
            if not p.exists():
                return None
            stat = p.stat()
            return FileMetadata(
                size=stat.st_size,
                mtime=stat.st_mtime
            )
        except OSError:
            return None

    def file_exists(self, filepath: str) -> bool:
        """Check if file exists on local filesystem."""
        try:
            return Path(filepath).exists()
        except OSError:
            return False

    def read_file_bytes(self, filepath: str) -> Optional[bytes]:
        """Read file from local filesystem."""
        try:
            p = Path(filepath)
            if not p.exists():
                return None
            return p.read_bytes()
        except OSError:
            return None


class CloudStorageAdapter(StorageAdapter):
    """Placeholder for future cloud storage backend (S3/GCS/etc).

    This stub exists to document the interface that a cloud implementation
    must satisfy. When we're ready to add cloud support:

    1. Add cloud SDK dependency (boto3 for S3, google-cloud-storage for GCS)
    2. Implement these methods using the cloud API
    3. Update get_storage_adapter() to return this based on config

    Key considerations for cloud implementation:
    - get_file_metadata: Use HEAD request or list with metadata
    - file_exists: Use HEAD request (cheaper than GET)
    - read_file_bytes: Use GET request, consider streaming for large files
    - get_files_metadata: Batch into single list operation where possible
    """

    def __init__(self, bucket: str, prefix: str = ""):
        """Initialize cloud storage adapter.

        Args:
            bucket: Cloud storage bucket name
            prefix: Optional prefix/folder within bucket
        """
        self.bucket = bucket
        self.prefix = prefix
        raise NotImplementedError(
            "CloudStorageAdapter is a placeholder. "
            "Implement with your cloud SDK when ready."
        )

    def get_file_metadata(self, filepath: str) -> Optional[FileMetadata]:
        raise NotImplementedError("Cloud storage not yet implemented")

    def file_exists(self, filepath: str) -> bool:
        raise NotImplementedError("Cloud storage not yet implemented")

    def read_file_bytes(self, filepath: str) -> Optional[bytes]:
        raise NotImplementedError("Cloud storage not yet implemented")


# Module-level singleton
_storage_adapter: Optional[StorageAdapter] = None


def get_storage_adapter() -> StorageAdapter:
    """Get the configured storage adapter (singleton).

    Returns LocalStorageAdapter by default. In the future, this could
    check an environment variable or config file to return a cloud adapter.

    Returns:
        The active StorageAdapter instance
    """
    global _storage_adapter
    if _storage_adapter is None:
        _storage_adapter = LocalStorageAdapter()
    return _storage_adapter


def compute_max_mtime(filepaths: List[str], adapter: Optional[StorageAdapter] = None) -> float:
    """Compute the maximum mtime across a list of files.

    This is a convenience function used for updated_at calculation.

    Args:
        filepaths: List of file paths to check
        adapter: Storage adapter (uses default if not provided)

    Returns:
        Maximum mtime as Unix timestamp, or 0.0 if no files exist
    """
    if adapter is None:
        adapter = get_storage_adapter()

    max_mtime = 0.0
    for fp in filepaths:
        meta = adapter.get_file_metadata(fp)
        if meta and meta.mtime > max_mtime:
            max_mtime = meta.mtime
    return max_mtime


def get_trackpack_updated_at(
    data: Dict[str, Any],
    db_updated_at: Optional[str] = None,
    db_created_at: Optional[str] = None,
    adapter: Optional[StorageAdapter] = None
) -> str:
    """Compute a consistent updated_at timestamp for a trackpack.

    Priority order:
    1. db_updated_at if present and valid
    2. max(mtime) of all audio files in the trackpack (via adapter)
    3. db_created_at if present and valid
    4. Current time as last resort

    Why mtime before created_at:
        Many MSS installs have older schemas with created_at but no updated_at.
        When users edit hints, swap audio files, or re-record, the file mtime
        changes but created_at remains fixed. Using mtime before created_at
        ensures updated_at reflects the actual last content change, not just
        when the profile row was first inserted.

    Args:
        data: Trackpack data dict with 'buttons' list containing 'filepath' keys
        db_updated_at: Optional updated_at from database (ISO8601 or SQLite format)
        db_created_at: Optional created_at from database (ISO8601 or SQLite format)
        adapter: Storage adapter (uses default if not provided)

    Returns:
        ISO 8601 timestamp string in UTC (e.g., "2026-01-31T18:42:10Z")
    """
    if adapter is None:
        adapter = get_storage_adapter()

    # Helper to parse DB timestamp
    def parse_db_timestamp(ts: Optional[str]) -> Optional[datetime.datetime]:
        if not ts:
            return None
        try:
            ts_str = str(ts)
            # Handle SQLite datetime format (YYYY-MM-DD HH:MM:SS)
            if 'T' not in ts_str:
                dt = datetime.datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                return dt.replace(tzinfo=datetime.timezone.utc)
            else:
                # ISO format - handle 'Z' suffix
                return datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None

    # Priority 1: DB updated_at (explicit tracking, most authoritative)
    dt = parse_db_timestamp(db_updated_at)
    if dt:
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Priority 2: Max mtime from audio files (reflects actual content changes)
    # This comes before created_at because older schemas lack updated_at,
    # but file mtimes still capture when audio/content was last modified.
    filepaths = [btn['filepath'] for btn in data.get('buttons', []) if btn.get('filepath')]
    max_mtime = compute_max_mtime(filepaths, adapter)

    if max_mtime > 0:
        dt = datetime.datetime.fromtimestamp(max_mtime, tz=datetime.timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Priority 3: DB created_at (better than nothing, but doesn't track edits)
    dt = parse_db_timestamp(db_created_at)
    if dt:
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Priority 4: Current time as last resort (should rarely happen)
    dt = datetime.datetime.now(tz=datetime.timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
