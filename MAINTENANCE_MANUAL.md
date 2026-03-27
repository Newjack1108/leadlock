# LeadLock — Operations & Maintenance Manual

This document describes how the Cheshire Stables LeadLock web app is structured, what to monitor, and what to maintain over time. It complements the setup guides in the repo (see [References](#references)).

---

## 1. What you are running

| Piece | Role |
|--------|------|
| **API** (`api/`) | FastAPI + Uvicorn; JWT auth; business logic; webhooks; PDF/email/SMS integrations |
| **Web** (`web/`) | Next.js (App Router); talks to the API via `NEXT_PUBLIC_API_URL` |
| **PostgreSQL** | Primary data store (e.g. Railway Postgres plugin) |
| **Optional services** | Backup cron job, S3-compatible storage for off-site backups |

The API creates/updates tables and runs **inline migrations** on startup (`create_db_and_tables()` in `api/app/database.py`). There is **no separate Alembic migration step** in production today—deploys apply schema changes when the container starts.

---

## 2. Deployment layout (Railway)

Typical setup:

- **API service**: build from repo root using `api/Dockerfile` (see root `railway.json`). **Root directory** is often empty so `Procfile` / `api/start.sh` paths resolve correctly—see `RAILWAY_FRONTEND_SETUP.md` for the API note.
- **Frontend service**: **Root directory must be `web`** or Railway may build the Python API by mistake. Use `web/Dockerfile` if Nixpacks causes runtime issues.
- **Postgres**: linked so `DATABASE_URL` is injected into the API.
- **Backup cron** (optional): separate service using `api/Dockerfile.backup`, volume at `/app/backups`, schedule e.g. `0 2 * * *` (UTC). See `BACKUP_SETUP.md`.

**Things to verify after any infra change**

- API has `DATABASE_URL`, strong `SECRET_KEY`, and correct `CORS_ORIGINS` including your real frontend origin(s).
- Frontend has `NEXT_PUBLIC_API_URL` set **before** build (public quote pages embed API calls at build time).
- API has a frontend base URL (`FRONTEND_BASE_URL` or `FRONTEND_URL` or `PUBLIC_FRONTEND_URL`) so quote emails and public links work.

---

## 3. Health checks & logs

| Endpoint / area | Use |
|-----------------|-----|
| `GET /health` | Lightweight check (no DB); confirms the API process is up (`api/app/main.py`). |
| Railway **Deployments → Logs** | First place for startup failures (DB SSL, missing env, import errors). |
| `DEBUG=true` | Exposes more error detail and SQL echo (local/dev); avoid leaving on in production unless troubleshooting briefly. |

**Background activity in the API process**

- **IMAP polling** (if IMAP is configured): thread polls on `IMAP_POLL_INTERVAL` (default 300 seconds). Misconfigured IMAP shows errors in logs but should not crash the app.
- **Scheduled SMS worker**: sends due `ScheduledSms` rows on `SMS_SCHEDULER_INTERVAL` (default 45 seconds). Requires Twilio env vars for actual sends.

---

## 4. Environment variables — awareness checklist

Group by risk so nothing critical is forgotten when rotating keys or cloning an environment.

### Core (API won’t behave correctly without these)

- `DATABASE_URL` — Postgres; non-local URLs get `sslmode=require` appended in code when needed.
- `SECRET_KEY` — JWT signing; **rotating it logs everyone out** (new tokens only).
- `CORS_ORIGINS` — Comma-separated list; **browser calls fail** if the live frontend origin is missing.

### Frontend ↔ API linking

- **Web**: `NEXT_PUBLIC_API_URL` — must match deployed API URL.
- **API**: `FRONTEND_BASE_URL` / `FRONTEND_URL` / `PUBLIC_FRONTEND_URL` — customer quote view links, PDFs, some public flows.

### Webhooks & automation

- `WEBHOOK_API_KEY` — Make.com (and similar) lead creation; treat as a secret.
- `WEBHOOK_DEFAULT_USER_ID` — Optional default assignee for webhook-created leads.
- `PRODUCT_IMPORT_API_KEY` — Product import; can fall back to `WEBHOOK_API_KEY` in code.

### Email (multiple backends; configure one coherent path)

- **Microsoft Graph** (recommended on Railway): `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID`, `MSGRAPH_FROM_EMAIL`, optional `MSGRAPH_FROM_NAME`, `GRAPH_INBOUND_TOP`, etc. (`MSGRAPH_EMAIL_SETUP.md`).
- **Resend**: `RESEND_API_KEY`, optional `RESEND_FROM_EMAIL`, `RESEND_FROM_NAME` (`RESEND_EMAIL_SETUP.md`).
- **SMTP/IMAP** (legacy/alternative): `SMTP_*`, `IMAP_*`, `EMAIL_TEST_MODE`, `SMTP_TIMEOUT`, `IMAP_POLL_INTERVAL`, `IMAP_SEARCH_MODE`, `IMAP_SINCE_DAYS`. SMTP can be flaky on some hosts; docs note this.

### SMS (Twilio)

- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- Webhook URL variables for inbound SMS (`TWILIO_SMS_WEBHOOK_URL`, activity attribution: `TWILIO_ACTIVITY_USER_ID`) — see `TWILIO_WEBHOOK.md`

### Facebook Messenger

- `FACEBOOK_PAGE_ACCESS_TOKEN`, `FACEBOOK_VERIFY_TOKEN`, `FACEBOOK_ACTIVITY_USER_ID` — see `FACEBOOK_MESSENGER_SETUP.md`

### Media & maps

- **Cloudinary** (optional): `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` — `CLOUDINARY_SETUP.md`
- **OpenRouteService** (optional): `OPENROUTE_SERVICE_API_KEY` — driving distance vs straight-line fallback

### PDF / branding helpers

- `LOGO_URL`, `LOGO_BASE_URL`, `EMAIL_BRAND_PRIMARY` — used in email/PDF branding paths

### Xero / Make automation

- `MAKE_XERO_WEBHOOK_URL` — outbound from app to Make (`make_xero_service.py`)

### Cross-environment or production-only API calls

- `PRODUCTION_APP_API_URL`, `PRODUCTION_APP_API_KEY` — used in orders flows when calling another deployment

### Backups (backup service only)

- `BACKUP_DIR`, `BACKUP_RETENTION_COUNT`, optional S3: `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`, `AWS_*` — `BACKUP_SETUP.md`

---

## 5. Database operations

### Schema changes

- Applied at **API startup** via SQLModel `create_all` plus **custom migration steps** in `database.py`.
- **Implication**: deploy order matters—always deploy API after pulling code that expects new columns. Watch logs for migration warnings.
- README still suggests considering **Alembic** for stricter production migrations; that is not wired in yet.

### Seeding users

- `api/seed.py` creates initial test users (documented in `README.md`). **Do not rely on default passwords in production**—change or replace users after first deploy.

### Backups & restore

- Follow `BACKUP_SETUP.md`: retention (default 5), cron UTC time, `pg_restore` procedure.
- Test a restore periodically on a **copy** of the database.

### Connection string quirks

- `postgres://` URLs are normalized to `postgresql://`.
- Remote connections add `sslmode=require` when appropriate (`database.py`).

---

## 6. Security & access

- **JWT**: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 1440) balances convenience vs risk.
- **Webhook and import keys**: rotate if exposed; update Make.com / automation at the same time.
- **CORS**: restrict to known origins in production; defaults in code include example Railway URLs—replace with your real domains.
- **User accounts**: `is_active` on users (migration in `database.py`) can disable access without deleting rows.
- **Director-only data**: company settings (e.g. bank details) are restricted in the API—keep API authentication strict.

---

## 7. Integrations — ongoing care

| Integration | Maintenance |
|-------------|-------------|
| **Make.com** | Webhook URL and `X-API-Key` must stay in sync with production API URL and `WEBHOOK_API_KEY`. See `MAKECOM_INTEGRATION_GUIDE.md`. |
| **Twilio** | Phone number, account status, webhook URLs for SMS status/inbound. |
| **Facebook** | Page tokens expire; verify token for webhook challenge. |
| **Microsoft / Resend** | App registrations, DNS (SPF/DKIM if using custom domains), API quotas. |
| **Cloudinary** | Usage limits and folder/ACL policies if used for uploads. |
| **OpenRouteService** | API key quotas and fair-use limits. |

---

## 8. Routine maintenance (suggested)

| Frequency | Task |
|-----------|------|
| **Weekly** | Skim API and frontend deploy logs for errors; check backup job success (if enabled). |
| **Monthly** | Confirm Railway billing, Postgres disk, and third-party (Twilio, email, maps) usage/costs. |
| **Quarterly** | Test backup restore; review user list and deactivate leavers; rotate webhook/API keys if policy requires. |
| **After dependency updates** | Run `pip install -r api/requirements.txt` and `npm ci` / `npm install` in `web/`, run builds locally, then deploy. |
| **After domain or URL change** | Update `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`, `FRONTEND_*`, and any webhooks in external systems. |

---

## 9. Common failure modes

| Symptom | Things to check |
|---------|-----------------|
| Browser “CORS” or blocked login | `CORS_ORIGINS` includes exact frontend origin (scheme + host + port). |
| Frontend builds but quote links broken | `NEXT_PUBLIC_API_URL` and API `FRONTEND_*` variables. |
| API won’t start | `DATABASE_URL`, SSL, Postgres up, recent migration errors in logs. |
| Emails not sending | Which provider is configured (Graph vs Resend vs SMTP); credentials; from-address validation. |
| Inbound email not appearing | Graph vs IMAP config; IMAP thread only processes mail for **known customers** (by email). |
| SMS stuck | Twilio credentials; scheduled worker logs; `TWILIO_PHONE_NUMBER`. |
| Webhook leads not created | URL path, `X-API-Key`, JSON body per `MAKECOM_INTEGRATION_GUIDE.md`. |
| Wrong app built on Railway | Frontend **root directory** = `web`; API not pointed at `web` by mistake. |

---

## 10. Local development (quick reference)

- **API**: Python 3.9+, `uvicorn app.main:app --reload --port 8000` from `api/` after venv + `requirements.txt`.
- **Web**: Node **≥ 20**, `npm install`, `NEXT_PUBLIC_API_URL=http://localhost:8000` in `web/.env.local`.
- **Static assets**: API serves `/static` and may copy logos from `web/public` on startup (`main.py`).

---

## References

| Document | Topic |
|----------|--------|
| `README.md` | Overview, env vars, workflow, deployment summary |
| `QUICKSTART.md` | Fast local setup |
| `RAILWAY_FRONTEND_SETUP.md` | Railway frontend pitfalls, API env for quotes |
| `BACKUP_SETUP.md` | Cron backup service, S3, restore |
| `MSGRAPH_EMAIL_SETUP.md` | Microsoft Graph |
| `RESEND_EMAIL_SETUP.md` | Resend |
| `CLOUDINARY_SETUP.md` | Image uploads |
| `FACEBOOK_MESSENGER_SETUP.md` | Messenger |
| `TWILIO_WEBHOOK.md` | SMS webhooks |
| `MAKECOM_INTEGRATION_GUIDE.md` | Lead webhooks |
| `XERO_SETUP.md` | Xero-related setup |
| `TRACKING_PIXEL.md` | Quote email tracking pixel |

---

*Proprietary — Cheshire Stables. Update this manual when deployment topology or critical env vars change.*
