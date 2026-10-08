# AGENTS.md

## Cursor Cloud specific instructions

LeadLock is a single product with two services that must both run for end-to-end use:

- `api/` — FastAPI + SQLModel backend (Python 3.11, pinned by `api/runtime.txt`).
- `web/` — Next.js 16 + TypeScript frontend (Node 20+; Node 22 is preinstalled).

The startup update script (see environment setup) already creates the backend venv at `api/venv`
and installs Python deps + `npm install` for the web app. Do not re-run dependency installation
by hand unless something is missing.

### Running the services (dev mode)

Backend (from `api/`, with the venv active):

```
. venv/bin/activate
export DATABASE_URL="sqlite:///./leadlock_dev.db"
export SECRET_KEY="dev-secret-key"
uvicorn app.main:app --reload --port 8000
```

Frontend (from `web/`): `npm run dev` (serves on `http://localhost:3000`, reads
`web/.env.local` → `NEXT_PUBLIC_API_URL=http://localhost:8000`).

### Non-obvious gotchas

- **Database for local dev:** the README targets PostgreSQL, but the app and the whole test
  suite run fine on SQLite. Set `DATABASE_URL=sqlite:///./leadlock_dev.db` for the backend.
  Without a `DATABASE_URL`, the app defaults to a non-existent Postgres at `localhost:5432` and
  will fail to connect. On SQLite you will see many `ALTER TYPE ... syntax error` warnings during
  startup/seed — these are Postgres-only enum migrations that are caught and safely ignored.
- **Seeding demo users:** `python seed.py` creates the three demo logins only if the users table
  is empty. Startup auto-creates a `system@leadlock.internal` user, so on an already-initialized DB
  `seed.py` prints "Users already exist" and skips. To (re)create the demo users
  (`director@cheshirestables.com` / `director123`, `manager@…` / `manager123`,
  `closer@…` / `closer123`) on a DB that already has the system user, insert them directly with a
  short script rather than relying on `seed.py`.
- **Test-only dependencies:** `pytest` is not in `requirements.txt`. The Starlette `TestClient`
  needs `httpx < 0.28` (httpx 0.28 removed the `app=` kwarg), and the anyio `[trio]` test
  parametrizations need `trio < 0.24` (anyio 3.7.1 references the removed `trio.MultiError`).
  These three are installed by the update script; they are not needed to run the app itself.
- **Pre-existing test/lint failures (not environment issues):** `cd api && pytest` currently shows
  ~479 passing and 16 failing. The failures are pre-existing in the repo (date-dependent
  weekly-plan tests plus behavioral configurator/outreach/phone-sync assertions) and reproduce
  identically on Python 3.11 and 3.12. `cd web && npm run lint` runs but reports many pre-existing
  errors/warnings in the app source. `cd web && npm test` (vitest) passes.

### Lint / test / build reference

- Backend tests: `cd api && . venv/bin/activate && python -m pytest`
- Frontend lint: `cd web && npm run lint`
- Frontend tests: `cd web && npm test`
- Frontend build: `cd web && npm run build`
