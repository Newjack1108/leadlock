# List page performance

## Baseline (before/after deploy)

In Chrome DevTools → Network (disable cache), while logged in on production:

| Endpoint | Page | What to note |
|----------|------|----------------|
| `GET /api/customers` | Customers | Waiting (TTFB) |
| `GET /api/dashboard/unread-by-customer` | Customers | Should load after list (deferred) |
| `GET /api/leads` | Leads | TTFB; check `includeTotal=false` when unfiltered |
| `GET /api/quotes` | Quotes | TTFB (largest win from list-mode batching) |

Healthy targets (same Railway project, private DB): list TTFB often **&lt; 1–3s**; **&gt; 10s** usually means DB contention, public proxy URL, or missing indexes.

## Railway checks

1. **Worker deploy logs:** `List/unread performance indexes ensured`
2. **API variables:** Prefer private `DATABASE_URL` (reference Postgres in same project). Use `DATABASE_USE_PUBLIC=true` only if private network times out.
3. **Migrations:** Worker only; API `API_SKIP_STARTUP_MIGRATIONS=true`

See [RAILWAY_RECOVERY.md](RAILWAY_RECOVERY.md) for deploy order and DB URL details.
