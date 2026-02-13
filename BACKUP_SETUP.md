# LeadLock Backup Setup

Daily PostgreSQL backups with 5-backup rotation. Backups are stored on a Railway Volume and can optionally be uploaded to S3 for off-site redundancy.

## Overview

- **Schedule**: Daily at 2:00 AM UTC
- **Retention**: 5 most recent backups (older ones are deleted)
- **Storage**: Railway Volume at `/app/backups`
- **Optional**: S3 upload for off-site copies

## Railway Setup

### 1. Create the Backup Cron Service

1. In your Railway project, click **+ New** → **GitHub Repo** (or use the existing repo)
2. Select the LeadLock repository
3. Configure the new service:
   - **Root Directory**: `api`
   - Add variable **`RAILWAY_DOCKERFILE_PATH`** = `api/Dockerfile.backup` (path from repo root) so Railway uses the backup Dockerfile with `postgresql-client`
4. In **Settings**:
   - **Start Command**: `python backup.py`
   - **Cron Schedule**: `0 2 * * *` (daily at 2:00 AM UTC)

### 2. Attach a Volume

1. In the backup service, go to **Volumes**
2. Click **+ Add Volume** (or **New Volume**)
3. Set **Mount Path**: `/app/backups`
4. Save

If writes fail with permission errors, add this variable to the backup service:
- `RAILWAY_RUN_UID=0`

### 3. Connect to PostgreSQL

The backup service needs `DATABASE_URL`. Either:

- **Link the Postgres service**: In the backup service, use **Variables** → **Add Reference** and reference `DATABASE_URL` from your Postgres service
- **Or** copy `DATABASE_URL` from your API/Postgres service into the backup service variables

### 4. Optional: S3 Upload

To upload each backup to S3, add these variables to the backup service:

| Variable | Description |
|----------|-------------|
| `BACKUP_S3_BUCKET` | S3 bucket name |
| `BACKUP_S3_PREFIX` | Optional key prefix (e.g. `leadlock/`) |
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_REGION` | Bucket region (e.g. `eu-west-1`) |

Compatible with AWS S3, Cloudflare R2, Backblaze B2, and other S3-compatible storage.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `BACKUP_DIR` | No | `/app/backups` | Directory for backup files |
| `BACKUP_RETENTION_COUNT` | No | `5` | Number of backups to keep |
| `BACKUP_S3_BUCKET` | No | - | S3 bucket for uploads |
| `BACKUP_S3_PREFIX` | No | - | S3 key prefix |
| `AWS_ACCESS_KEY_ID` | If S3 | - | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | If S3 | - | AWS credentials |
| `AWS_REGION` | If S3 | - | Bucket region |

## Local Testing

1. Ensure PostgreSQL client tools are installed (`pg_dump`):
   - **Ubuntu/Debian**: `sudo apt-get install postgresql-client`
   - **macOS**: `brew install libpq` (or Postgres.app)
   - **Windows**: Install PostgreSQL (includes client tools)

2. Set up `.env` in the `api/` directory with `DATABASE_URL`

3. Run the backup:
   ```bash
   cd api
   BACKUP_DIR=./backups python backup.py
   ```

4. Backups appear in `api/backups/` as `leadlock_YYYY-MM-DD_HHMMSS.dump`

## Restoring a Backup

Backups use PostgreSQL custom format (`-F c`). To restore:

```bash
# Drop and recreate the database (destructive!)
psql -d postgres -c "DROP DATABASE IF EXISTS leadlock;"
psql -d postgres -c "CREATE DATABASE leadlock;"

# Restore
pg_restore -d "postgresql://user:password@host:port/leadlock" -F c --no-owner --no-acl leadlock_2025-02-13_020000.dump
```

Or use the connection string from your `DATABASE_URL`:

```bash
pg_restore -d "$DATABASE_URL" -F c --no-owner --no-acl leadlock_2025-02-13_020000.dump
```

## Cron Notes

- Railway cron services **must exit** when done. The backup script exits with code 0 on success, non-zero on failure.
- If a previous run is still in progress when the next schedule hits, Railway skips the new run. Keep backups fast (they usually complete in seconds for typical LeadLock databases).
- Cron times are in **UTC**.
