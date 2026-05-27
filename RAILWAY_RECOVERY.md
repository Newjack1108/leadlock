# Railway recovery checklist (API 502 / empty app)

## Symptom: frontend loads but no data / login fails

1. Check API health: `https://leadlock-production.up.railway.app/health`
   - `"status": "ok"` and `"database": "ok"` and `"migrations": "complete"` → fully ready.
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

## Symptom: `/health` returns 502

The container is not listening. Check **Deploy logs** for `Database startup failed` or missing `DATABASE_URL`.
