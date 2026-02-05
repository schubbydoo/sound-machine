"""Entry point for running MSS backend directly.

Usage:
    python -m web_interface.backend          # Run with defaults
    python -m web_interface.backend --help   # Show options

Environment variables:
    MSS_ROOT       - Project root directory
    MSS_DATA_DIR   - Data directory (DB, exports)
    MSS_SOUNDS_DIR - Audio files directory
    MSS_DB_PATH    - Database file path (direct override)
"""

import argparse
import sys

from .config import config


def main():
    parser = argparse.ArgumentParser(
        description='MSS Backend Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--host', default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port', type=int, default=8080,
        help='Port to bind to (default: 8080)'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable Flask debug mode'
    )
    parser.add_argument(
        '--init-db', action='store_true',
        help='Initialize database before starting (if not exists)'
    )
    parser.add_argument(
        '--validate-only', action='store_true',
        help='Only validate configuration, do not start server'
    )

    args = parser.parse_args()

    # Validate-only mode: just check config and exit
    if args.validate_only:
        print("Configuration validation:")
        for key, value in config.validate().items():
            status = "OK" if (isinstance(value, bool) and value) or \
                           (isinstance(value, str) and value) else "MISSING"
            if not isinstance(value, bool):
                status = value
            print(f"  {key}: {status}")
        sys.exit(0)

    # Initialize database if requested
    if args.init_db:
        if not config.db_path.exists():
            print(f"[MSS] Initializing database at {config.db_path}")
            # Import here to avoid circular imports
            sys.path.insert(0, str(config.root))
            from db.init_db import init_db
            init_db(config.db_path)
        else:
            print(f"[MSS] Database already exists at {config.db_path}")

    # Import app here (after potential DB init) to trigger startup logging
    from .app import app

    # Check if DB exists, warn if not
    if not config.db_path.exists():
        print(f"[MSS] WARNING: Database not found at {config.db_path}")
        print(f"[MSS] Run with --init-db or: python -m db.init_db")

    # Run the Flask development server
    print(f"[MSS] Starting server on {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
