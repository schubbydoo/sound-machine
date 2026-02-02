"""Server identity management for MSS backend.

Provides stable, persistent identification for MSS instances. The server_id
survives restarts and reboots, enabling future features like:
- Cloud sync pairing
- Multi-device coordination
- Update tracking

Usage:
    from backend.server_identity import get_server_id, get_server_name

    server_id = get_server_id(data_dir)    # "mss-local-a1b2c3d4-..."
    server_name = get_server_name(data_dir) # "Memory Spark Station" or custom
"""

import uuid
from pathlib import Path
from typing import Optional

# File names within data directory
SERVER_ID_FILE = "server_id.txt"
SERVER_NAME_FILE = "server_name.txt"

# Defaults
DEFAULT_SERVER_NAME = "Memory Spark Station"
SERVER_ID_PREFIX = "mss-local-"


def get_server_id(data_dir: Path) -> str:
    """Get or create a stable server identifier.

    On first run, generates a random UUID4 and persists it.
    On subsequent runs, reads the persisted value.
    If the file is missing, empty, or unreadable, regenerates.

    Args:
        data_dir: Path to the writable data directory

    Returns:
        Server ID in format "mss-local-<uuid4>"
    """
    id_file = data_dir / SERVER_ID_FILE

    # Try to read existing ID
    raw_id = _read_file_content(id_file)
    if raw_id:
        # Validate it looks like a UUID (basic check)
        if _is_valid_server_id(raw_id):
            print(f"[SERVER] Loaded server_id from {SERVER_ID_FILE}")
            return raw_id

    # Generate new ID
    new_uuid = str(uuid.uuid4())
    new_id = f"{SERVER_ID_PREFIX}{new_uuid}"

    # Persist it
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        id_file.write_text(new_id, encoding="utf-8")
        print(f"[SERVER] Generated new server_id and persisted it")
    except OSError as e:
        print(f"[SERVER] Warning: Could not persist server_id: {e}")

    return new_id


def get_server_name(data_dir: Path) -> str:
    """Get the server display name.

    Reads from server_name.txt if it exists and has content.
    Otherwise returns the default name.

    Args:
        data_dir: Path to the writable data directory

    Returns:
        Human-friendly server name
    """
    name_file = data_dir / SERVER_NAME_FILE

    custom_name = _read_file_content(name_file)
    if custom_name:
        print(f"[SERVER] Loaded server_name from file")
        return custom_name

    print(f"[SERVER] Using default server_name")
    return DEFAULT_SERVER_NAME


def _read_file_content(filepath: Path) -> Optional[str]:
    """Read and return file content, stripped of whitespace.

    Returns None if file doesn't exist, is empty, or unreadable.
    """
    try:
        if not filepath.exists():
            return None
        content = filepath.read_text(encoding="utf-8").strip()
        return content if content else None
    except OSError:
        return None


def _is_valid_server_id(server_id: str) -> bool:
    """Basic validation that server_id looks correct.

    Checks that it starts with the expected prefix and has reasonable length.
    """
    if not server_id:
        return False
    if not server_id.startswith(SERVER_ID_PREFIX):
        return False
    # UUID4 is 36 chars, prefix is ~10 chars, so total should be ~46+
    if len(server_id) < 40:
        return False
    return True
