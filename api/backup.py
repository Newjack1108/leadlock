#!/usr/bin/env python3
"""
Daily PostgreSQL backup script with 5-backup rotation.
Stores backups on a Railway Volume; optionally uploads to S3.
Run as Railway cron or manually with DATABASE_URL in env.
"""
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Load .env if present (local dev)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Backup directory: /app/backups on Railway, ./backups locally
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/app/backups"))
RETENTION = int(os.getenv("BACKUP_RETENTION_COUNT", "5"))

# S3 config (optional)
S3_BUCKET = os.getenv("BACKUP_S3_BUCKET", "").strip()
S3_PREFIX = os.getenv("BACKUP_S3_PREFIX", "").strip().rstrip("/")


def get_database_url() -> str:
    """Get and normalize DATABASE_URL for pg_dump."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    # postgres:// -> postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[9:]

    # Railway Postgres: add sslmode for non-localhost
    if "localhost" not in url and "127.0.0.1" not in url:
        if "sslmode=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}sslmode=require"

    return url


def run_pg_dump(url: str, out_path: Path) -> bool:
    """Run pg_dump; return True on success."""
    # Use custom format (-F c) for compressed, restorable dumps
    cmd = [
        "pg_dump",
        "-d", url,
        "-F", "c",
        "-f", str(out_path),
        "--no-owner",
        "--no-acl",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pg_dump failed: {e.stderr or e}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("ERROR: pg_dump not found. Install postgresql-client.", file=sys.stderr)
        return False


def rotate_backups(backup_dir: Path, retention: int) -> None:
    """Keep only the `retention` most recent backup files; delete the rest."""
    if retention < 1:
        return
    # Match *.dump files (pg_dump custom format)
    pattern = re.compile(r"^leadlock_\d{4}-\d{2}-\d{2}_\d{6}\.dump$")
    backups = [
        f for f in backup_dir.iterdir()
        if f.is_file() and pattern.match(f.name)
    ]
    backups.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    for old in backups[retention:]:
        try:
            old.unlink()
            print(f"Removed old backup: {old.name}", file=sys.stderr)
        except OSError as e:
            print(f"Warning: could not remove {old.name}: {e}", file=sys.stderr)


def upload_to_s3(local_path: Path, object_key: str) -> bool:
    """Upload file to S3. Returns True on success."""
    if not S3_BUCKET:
        return True
    try:
        import boto3
    except ImportError:
        print("ERROR: boto3 not installed. Install it for S3 upload.", file=sys.stderr)
        return False

    try:
        client = boto3.client("s3")
        key = f"{S3_PREFIX}/{object_key}".lstrip("/") if S3_PREFIX else object_key
        client.upload_file(str(local_path), S3_BUCKET, key)
        print(f"Uploaded to s3://{S3_BUCKET}/{key}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"ERROR: S3 upload failed: {e}", file=sys.stderr)
        return False


def main() -> None:
    url = get_database_url()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    filename = f"leadlock_{ts}.dump"
    out_path = BACKUP_DIR / filename

    print(f"Creating backup: {out_path}", file=sys.stderr)
    if not run_pg_dump(url, out_path):
        sys.exit(1)

    rotate_backups(BACKUP_DIR, RETENTION)

    if S3_BUCKET:
        if not upload_to_s3(out_path, filename):
            print("Warning: S3 upload failed; local backup kept.", file=sys.stderr)
            # Don't exit 1 - backup succeeded locally

    print(f"Backup completed: {out_path}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
