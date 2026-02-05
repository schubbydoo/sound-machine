"""MSS Backend Configuration

Centralized configuration for all filesystem paths and settings.
Supports three deployment modes:
  - Local dev: Auto-detects project root from file location
  - Pi mode: Uses /home/soundconsole/sound-machine if it exists
  - Cloud/VM mode: Uses environment variables for full control

Configuration priority (highest to lowest):
  1. Specific env vars (MSS_DATA_DIR, MSS_SOUNDS_DIR, etc.)
  2. Paths derived from MSS_ROOT if set
  3. Auto-detected project root (for development)
  4. Legacy Pi paths (backward compatibility only if path exists)

Usage:
    from backend.config import config

    db_path = config.db_path
    sounds_dir = config.sounds_dir

    # At startup (called automatically by app.py):
    config.startup()  # logs paths, creates dirs, validates
"""

import os
import sys
from pathlib import Path
from typing import Optional, List


# Legacy Pi deployment path (backward compatibility)
_LEGACY_PI_ROOT = Path('/home/soundconsole/sound-machine')


def _detect_project_root() -> Path:
    """Detect project root by walking up from this file.

    Returns the directory containing web_interface/backend/config.py,
    which should be the project root.
    """
    # This file: {project_root}/web_interface/backend/config.py
    config_file = Path(__file__).resolve()
    backend_dir = config_file.parent          # web_interface/backend/
    web_interface_dir = backend_dir.parent    # web_interface/
    project_root = web_interface_dir.parent   # project root
    return project_root


def _get_root() -> Path:
    """Determine the application root directory.

    Priority:
    1. MSS_ROOT environment variable
    2. Auto-detected from this file's location (development)
    3. Legacy Pi path if it exists (production Pi)
    4. Auto-detected path as final fallback
    """
    # Explicit environment variable takes priority
    env_root = os.environ.get('MSS_ROOT')
    if env_root:
        return Path(env_root)

    # Auto-detect from file location (works in dev and most deployments)
    detected = _detect_project_root()

    # If legacy Pi path exists and detected path doesn't look like a real install,
    # prefer the legacy path for backward compatibility
    if _LEGACY_PI_ROOT.exists() and not (detected / 'web_interface').exists():
        return _LEGACY_PI_ROOT

    return detected


class Config:
    """Application configuration with lazy initialization.

    All paths are resolved once on first access and cached.
    Environment variables are read at initialization time.
    """

    def __init__(self):
        self._root: Optional[Path] = None
        self._data_dir: Optional[Path] = None
        self._sounds_dir: Optional[Path] = None
        self._config_dir: Optional[Path] = None
        self._log_dir: Optional[Path] = None
        self._db_path: Optional[Path] = None
        self._exports_dir: Optional[Path] = None

    @property
    def root(self) -> Path:
        """Project root directory."""
        if self._root is None:
            self._root = _get_root()
        return self._root

    @property
    def data_dir(self) -> Path:
        """Data directory for DB, exports, server identity."""
        if self._data_dir is None:
            env_val = os.environ.get('MSS_DATA_DIR')
            if env_val:
                self._data_dir = Path(env_val)
            else:
                self._data_dir = self.root / 'data'
        return self._data_dir

    @property
    def sounds_dir(self) -> Path:
        """Audio files directory (Sounds/)."""
        if self._sounds_dir is None:
            env_val = os.environ.get('MSS_SOUNDS_DIR')
            if env_val:
                self._sounds_dir = Path(env_val)
            else:
                self._sounds_dir = self.root / 'Sounds'
        return self._sounds_dir

    @property
    def config_dir(self) -> Path:
        """Configuration directory for wifi.json, bt.json."""
        if self._config_dir is None:
            env_val = os.environ.get('MSS_CONFIG_DIR')
            if env_val:
                self._config_dir = Path(env_val)
            else:
                self._config_dir = self.root / 'config'
        return self._config_dir

    @property
    def log_dir(self) -> Path:
        """Log directory."""
        if self._log_dir is None:
            env_val = os.environ.get('MSS_LOG_DIR')
            if env_val:
                self._log_dir = Path(env_val)
            else:
                self._log_dir = self.root / 'log'
        return self._log_dir

    @property
    def db_path(self) -> Path:
        """SQLite database file path."""
        if self._db_path is None:
            env_val = os.environ.get('MSS_DB_PATH')
            if env_val:
                self._db_path = Path(env_val)
            else:
                self._db_path = self.data_dir / 'sound_machine.db'
        return self._db_path

    @property
    def exports_dir(self) -> Path:
        """Trackpack exports directory."""
        if self._exports_dir is None:
            # No separate env var - always derived from data_dir
            self._exports_dir = self.data_dir / 'exports'
        return self._exports_dir

    @property
    def wifi_config_path(self) -> Path:
        """WiFi configuration file path."""
        return self.config_dir / 'wifi.json'

    @property
    def bt_config_path(self) -> Path:
        """Bluetooth configuration file path."""
        return self.config_dir / 'bt.json'

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist.

        Called at application startup to ensure all writable directories
        are available. Only creates directories within configured paths.

        Raises:
            OSError: If directory creation fails (permissions, disk full, etc.)
        """
        directories = [
            self.data_dir,
            self.exports_dir,
            self.sounds_dir,
            self.sounds_dir / 'uploads',
            self.config_dir,
            self.log_dir,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def validate(self) -> dict:
        """Validate configuration and return status report.

        Returns a dict with validation results for debugging/logging.
        Does not raise exceptions - caller decides how to handle issues.
        """
        results = {
            'root': str(self.root),
            'root_exists': self.root.exists(),
            'data_dir': str(self.data_dir),
            'data_dir_exists': self.data_dir.exists(),
            'db_path': str(self.db_path),
            'db_exists': self.db_path.exists(),
            'sounds_dir': str(self.sounds_dir),
            'sounds_dir_exists': self.sounds_dir.exists(),
            'config_dir': str(self.config_dir),
            'config_dir_exists': self.config_dir.exists(),
            'log_dir': str(self.log_dir),
            'log_dir_exists': self.log_dir.exists(),
        }
        return results

    def __repr__(self) -> str:
        return (
            f"Config(\n"
            f"  root={self.root},\n"
            f"  data_dir={self.data_dir},\n"
            f"  sounds_dir={self.sounds_dir},\n"
            f"  config_dir={self.config_dir},\n"
            f"  log_dir={self.log_dir},\n"
            f"  db_path={self.db_path}\n"
            f")"
        )

    def _log(self, message: str) -> None:
        """Print a startup log message."""
        print(f"[MSS] {message}", file=sys.stderr)

    def startup(self, fail_fast: bool = True) -> List[str]:
        """Initialize the application: log paths, create directories, validate.

        This is the single entry point for application startup. It:
        1. Logs all resolved paths (so operators know what's configured)
        2. Creates required directories
        3. Validates the configuration
        4. Optionally fails fast on critical errors

        Args:
            fail_fast: If True, exit with error on critical misconfiguration.
                      If False, return list of errors for caller to handle.

        Returns:
            List of error messages (empty if all is well).
        """
        errors: List[str] = []

        # Log resolved configuration
        self._log("=" * 50)
        self._log("MSS Backend Starting")
        self._log("=" * 50)
        self._log(f"Root:       {self.root}")
        self._log(f"Data dir:   {self.data_dir}")
        self._log(f"Sounds dir: {self.sounds_dir}")
        self._log(f"Config dir: {self.config_dir}")
        self._log(f"Log dir:    {self.log_dir}")
        self._log(f"DB path:    {self.db_path}")
        self._log("-" * 50)

        # Log which env vars are active
        env_vars = ['MSS_ROOT', 'MSS_DATA_DIR', 'MSS_SOUNDS_DIR',
                    'MSS_CONFIG_DIR', 'MSS_LOG_DIR', 'MSS_DB_PATH']
        active_env = [v for v in env_vars if os.environ.get(v)]
        if active_env:
            self._log(f"Active env vars: {', '.join(active_env)}")
        else:
            self._log("No MSS_* env vars set (using auto-detected paths)")

        # Create directories
        try:
            self.ensure_directories()
            self._log("Directories: OK (created/verified)")
        except OSError as e:
            msg = f"Failed to create directories: {e}"
            errors.append(msg)
            self._log(f"Directories: FAILED - {e}")

        # Validate root exists
        if not self.root.exists():
            msg = f"Root directory does not exist: {self.root}"
            errors.append(msg)
            self._log(f"Validation: FAILED - {msg}")

        # Check database
        if self.db_path.exists():
            self._log(f"Database: OK (exists)")
        else:
            self._log(f"Database: NOT FOUND (will be created on first request)")
            self._log(f"  Run: python -m db.init_db")

        # Check for Pi-specific environment
        is_pi = _is_raspberry_pi()
        self._log(f"Hardware: {'Raspberry Pi detected' if is_pi else 'Standard Linux/VM'}")

        self._log("=" * 50)

        # Handle errors
        if errors and fail_fast:
            self._log("FATAL: Configuration errors prevent startup")
            for err in errors:
                self._log(f"  - {err}")
            sys.exit(1)

        return errors


def _is_raspberry_pi() -> bool:
    """Check if we're running on a Raspberry Pi.

    Used for informational logging only - does not affect behavior.
    """
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except (IOError, OSError):
        return False


# Module-level singleton
config = Config()
