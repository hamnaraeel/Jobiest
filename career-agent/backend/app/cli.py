"""Local backup command (spec section 64).

Usage:
    python -m app.cli backup
    python -m app.cli backup --include-browser-profile

Backs up the full database (via pg_dump) and a snapshot of non-secret
configuration metadata into data/backups/{timestamp}/. Never backs up
`DATABASE_URL` (may contain credentials) or `OPENAI_API_KEY`, and never
backs up the browser profile (cookies/session state) unless explicitly
requested with --include-browser-profile.
"""

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings

_SECRET_SETTINGS_KEYS = ("database_url", "openai_api_key")


def _project_root() -> Path:
    # career-agent/backend/app/cli.py -> parents[2] is career-agent/,
    # matching where data/cvs, data/application_materials, etc already
    # live (same resolution pattern as browser_manager.py's _profile_dir()).
    return Path(__file__).resolve().parents[2]


def _backup_root() -> Path:
    path = _project_root() / "data" / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_settings_snapshot() -> dict:
    settings = get_settings()
    data = settings.model_dump()
    for key in _SECRET_SETTINGS_KEYS:
        data.pop(key, None)
    return data


def backup(include_browser_profile: bool = False) -> Path:
    settings = get_settings()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = _backup_root() / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_url = settings.database_url.replace("postgresql+psycopg2", "postgresql")
    dump_path = backup_dir / "database.sql"
    result = subprocess.run(
        ["pg_dump", "--no-owner", "--no-privileges", "-f", str(dump_path), db_url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")

    (backup_dir / "metadata.json").write_text(json.dumps(_safe_settings_snapshot(), indent=2, default=str))

    if include_browser_profile:
        profile_src = _project_root() / "backend" / settings.browser_profile_dir
        if profile_src.exists():
            shutil.copytree(profile_src, backup_dir / "browser_profile", dirs_exist_ok=True)

    return backup_dir


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="Back up the database and configuration metadata.")
    backup_parser.add_argument(
        "--include-browser-profile", action="store_true",
        help="Also copy data/browser_profile/ (cookies/session state) -- off by default.",
    )

    args = parser.parse_args()
    if args.command == "backup":
        path = backup(include_browser_profile=args.include_browser_profile)
        print(f"Backup written to {path}")


if __name__ == "__main__":
    main()
