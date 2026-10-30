# Free cloud staging: Render + Neon

This runbook is for **synthetic staging only**. It does not authorize cloud
resource creation, migration, real salon data, live sales, or `reserved_v1`
activation. The local Caddy template remains for a different hosting topology.

## One-origin runtime

- Build the repository `Dockerfile` as one Render **Free Web Service**. Render
  terminates HTTPS. One Uvicorn process serves `/api/v1` and the built React
  files on the service's `https://<name>.onrender.com` origin. The startup
  script binds `$PORT`; it never runs Alembic.
- Set manual deploys during staged cutover. Avoid overlapping old/new sale
  writers. Keep `SALE_ATTEMPT_PROTOCOL_ENABLED=0` in this foundation release.
- The public URL works from salon Wi-Fi while the Owner PC is off, provided
  the salon has internet. It is not restricted to the salon network.
- Render Free can sleep or restart. The filesystem is ephemeral. Neon Free can
  scale to zero and has limited restore history. Neither Free tier is suitable
  for live financial operations or the 14-day backup requirement.

## Protected Render environment

Set these in the Render dashboard, never in Git or the Docker image:

| Variable | Staging value or rule |
| --- | --- |
| `APP_ENV` | `production` to enable fail-closed startup checks |
| `AUTH_COOKIE_MODE` | `production` for Secure, HttpOnly host-only cookies |
| `AUTH_ALLOWED_ORIGIN` | Exact Render HTTPS origin, no path/trailing slash |
| `AUTH_RATE_LIMIT_SECRET` | Stable cryptographically random value, at least 32 bytes |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Neon **direct** endpoint and dedicated staging credentials |
| `DB_EXPECTED_NAME` | Same staging database name as `DB_NAME` |
| `DB_SSLMODE` | `verify-full` (certificate and hostname verification) |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | `2`, `0` for one staging worker |
| `SALE_ATTEMPT_PROTOCOL_ENABLED` | `0` until separately approved cutover |

Do not copy `backend/.env` from development. The Docker context excludes it.
Do not use the pooled Neon hostname for Alembic. Runtime also starts with the
direct hostname; test transaction-scoped locks on Neon before considering the
pooler. Never print the connection URL or secrets in a deployment log.

## Staging setup after separate resource and migration approvals

1. Create an isolated Neon Free project/database and dedicated staging role.
   Keep it empty of real salon data. Record its expected name privately.
2. Before any migration, independently verify the configured **and connected**
   database name, user, host, schema, and existing Alembic revision. Inspect
   unexpected records. Stop if the target is ambiguous.
3. With the application stopped, use a trusted operator machine and the Neon
   **direct TLS** endpoint to run Alembic to `20261027_01`. This requires a
   separate migration approval. Verify the final revision and `sale_attempts`
   constraints. Never migrate as an application startup command.
4. Create one Render Free Docker web service from the reviewed commit. Turn off
   automatic deploys. Set only protected staging environment variables. Do not
   choose paid resources or enable reserved mode.
5. Provision synthetic Owner/Cashier accounts only through a separately
   reviewed guarded workflow with hidden password prompts; never reuse local
   development accounts or publish test credentials.

## Smoke test before staging acceptance

- Confirm `/health`, React `/`, static assets, a client-side route, and a real
  JSON 404 for unknown `/api/v1` routes on the same HTTPS origin.
- With synthetic accounts, check login, `/auth/me`, logout, Owner/Cashier RBAC,
  Secure/HttpOnly cookie, Origin/CSRF rejection, and capability `legacy`.
- Verify actual login rate-limit client IP behavior behind Render. This Docker
  startup **does not trust forwarded headers**; until a verified proxy trust
  design is approved, the app may see a shared proxy IP. Do not treat an
  arbitrary `X-Forwarded-For` as the client IP.
- Exercise only synthetic Direct/Manual sales and reporting after a separate
  staging-data approval. Check idempotency, pending recovery, and cleanup.
- Check usage quotas, cold starts, and DB reconnection. Keep live sales off.

`reserved_v1` activation requires a separate coordinated pause, worker drain,
capability check, and Owner/Cashier acceptance. Follow the Deployment and
Activation Runbook; do not flip the gate during an ordinary rolling deploy.
