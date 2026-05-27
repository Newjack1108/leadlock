# Railway recovery checklist (API 502 / empty app)

## Symptom: frontend loads but no data / login fails

1. Check API health: `https://leadlock-production.up.railway.app/health`
   - `"status": "ok"` and `"database": "ok"` and `"migrations": "complete"` → fully ready.
   - `"row_counts": { "customers": N, "leads": N, "users": N }` → API sees that many rows (compare with Postgres Query tab). If Query shows thousands but `row_counts` is 0, API is on the wrong database URL.
   - `"database": "ok"` and `"migrations": "running"` → **you can use the app**; startup migrations still running (normal for 1–10 min on large DBs).
   - `"database": "initializing"` → API cannot reach Postgres yet; check `DATABASE_URL` (use `postgres.railway.internal` from the Postgres service reference).
   - `"database": "error"` → read `database_error` and fix `DATABASE_URL` (below).

2. **Railway → leadlock (API) → Variables**
   - `DATABASE_URL` must be a **reference** to your **existing** Postgres service (not a new empty DB).
   - `SECRET_KEY` must be set (unchanged from before today).
   - `CORS_ORIGINS` must include `https://leadlock-frontend-production.up.railway.app`  
     Or **delete** `CORS_ORIGINS` if it is blank so defaults apply.

3. **Railway → Postgres → Data / Query**
   ```sql
   SELECT COUNT(*) FROM customer;
   SELECT COUNT(*) FROM "user";
   ```
   - Counts **> 0** → data exists; fix API URL / auth / CORS.
   - Counts **0** → wrong database or data loss → restore from **Backup** service volume or S3 (`BACKUP_SETUP.md`).

4. **Redeploy** the `leadlock` API service after fixing variables.

## Symptom: Railway “Application failed to respond” (502)

Railway’s edge could not get a timely response from your container.

1. **Which URL fails?**
   - `https://leadlock-production.up.railway.app` → **API** service.
   - `https://www.csgbsales.co.uk` → usually **frontend** service (custom domain). Fix the service that is red in Railway.

2. **API → Deployments → View logs** (latest deploy). Look for:
   - `HTTP server ready` / `Uvicorn running` → process started; if you still get 502, health check or Postgres may be timing out.
   - `ModuleNotFoundError` / `ImportError` → broken deploy; redeploy from a good commit.
   - `Database connection failed` / `Connection timed out` → Postgres or `DATABASE_PUBLIC_URL` (see below).
   - Crash loop right after start → check **Settings → Health Check Path** is `/health/live` (not a slow DB-only path).

3. **Postgres** service must be **Online**. On **leadlock (API)** variables:
   - `DATABASE_USE_PUBLIC` = `true`
   - `DATABASE_PUBLIC_URL` = reference to Postgres → `DATABASE_PUBLIC_URL`
   - Redeploy API.

4. **Restart**: Postgres → Restart, then API → Redeploy. Wait 2–5 minutes; open `/health/live` (should be instant), then `/health`.

5. **Health check** (Railway → API service → Settings): Path **`/health/live`**, timeout **120s**. Do not use `/health` alone if the DB is slow — it runs `SELECT 1` and can fail deploy health checks.

## Symptom: `/health` returns 502

The container is not listening. Check **Deploy logs** for `Database startup failed` or missing `DATABASE_URL`.

## Symptom: `connection to postgres.railway.internal ... Connection timed out`

The API **cannot reach Postgres on Railway’s private network**. The URL format is fine; the **network path** is broken.

**Fix (try in order):**

1. **Same Railway project** — `leadlock` (API), `LeadLock Frontend`, `Postgres`, and `Worker` must all be in **one** project (not a copy of the repo in a second project).

2. **Link services in the UI** (best fix):
   - Open the **Postgres** service → **Connect** (or **Variables** / service connections).
   - Connect it to the **leadlock** API service (and Worker if used).
   - On **leadlock** → **Variables**, use **Add reference** → Postgres → `DATABASE_URL` (do not paste a URL copied from another project).

3. **Confirm Postgres is running** — Postgres service status **Online**, not crashed or deploying.

4. **Workaround: public TCP URL** (if private network still times out):
   - On **Postgres** → **Variables**, find **`DATABASE_PUBLIC_URL`** (host looks like `*.proxy.rlwy.net` or similar).
   - On **leadlock** → **Variables**, add:
     - `DATABASE_USE_PUBLIC` = `true`
     - `DATABASE_PUBLIC_URL` = **reference** to Postgres → `DATABASE_PUBLIC_URL`
   - Redeploy **leadlock**. The app will use the public proxy (still works from Railway; slightly different routing).

5. **Do not** point `DATABASE_URL` at a Postgres instance from a **different** Railway project or a deleted service — DNS may resolve but nothing listens → timeout.

After a successful connection, deploy logs should show `Database connection OK`. Then check row counts in Postgres Query tab.
