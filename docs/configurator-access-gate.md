# Configurator Access Gate

The configurator is gated as a feature capability, not a global user role.

## Phase 1: Railway Env Allowlist

Set these Railway environment variables on the API service:

```env
CONFIGURATOR_ENABLED=true
CONFIGURATOR_ALLOWED_EMAILS=kelvin@example.com
CONFIGURATOR_ALLOW_DIRECTOR_OVERRIDE=false
```

### Behavior

- `CONFIGURATOR_ENABLED=false` blocks everyone.
- Dealer accounts are always blocked.
- `CONFIGURATOR_ALLOWED_EMAILS` is a comma-separated allowlist of staff emails.
- Email matching is normalized with trim + lowercase.
- `CONFIGURATOR_ALLOW_DIRECTOR_OVERRIDE=true` lets directors bypass the allowlist.

### Kill Switch

To disable the configurator immediately in production without a rollback:

```env
CONFIGURATOR_ENABLED=false
```

That removes backend access even if the hidden route or cached UI link is still known.

## Current Backend Contract

The backend computes configurator capability in `api/app/auth.py` and returns it from:

- `GET /api/auth/me`

Response shape includes:

```json
{
  "id": 1,
  "email": "kelvin@example.com",
  "full_name": "Kelvin",
  "role": "DIRECTOR",
  "can_access_configurator": true
}
```

There is also a guarded feature endpoint:

- `GET /api/configurator/access`

This endpoint returns `403` for blocked users and is used by the hidden staff route to confirm backend enforcement.

## Frontend Behavior

- Normal users do not see the configurator navigation link.
- Allowlisted staff see a hidden beta entry in the header at `/quotes/configure`.
- Direct URL access still depends on backend authorization.
- Existing quote create/edit flows remain unchanged.

## Later Upgrade Path: Persisted User Flag

After the configurator is stable, replace email-only rollout with a user-level boolean:

- add `User.can_access_configurator` in `api/app/models.py`
- add an additive startup migration in `api/app/database.py`
- expose the field in user admin APIs and `/api/auth/me`

### Recommended Transition Logic

Use hybrid access evaluation temporarily:

1. `CONFIGURATOR_ENABLED` must still be `true`
2. access is granted when either:
   - the email is in `CONFIGURATOR_ALLOWED_EMAILS`, or
   - `User.can_access_configurator == true`

After the rollout is complete, the env allowlist can be retired, but `CONFIGURATOR_ENABLED` should remain as the permanent global kill switch.
