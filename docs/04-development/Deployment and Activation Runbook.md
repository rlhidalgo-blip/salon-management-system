# Single-salon deployment and reserved sale cutover

This is a deployment template, not an activation record. Only the chosen host's
operator should fill in its paths, domain, service manager and protected secrets.
Never copy the local `backend/.env` to production.

## Runtime boundary

- Build React once; serve `frontend/dist` and `/api/v1` on one HTTPS origin using
  `deploy/Caddyfile.example` as a template. Bind FastAPI to `127.0.0.1:8000`.
- Start Uvicorn with `--proxy-headers --forwarded-allow-ips 127.0.0.1` and do
  not expose its port publicly. Caddy replaces `X-Forwarded-For` with the IP it
  directly observes. If another proxy is introduced, review this trust boundary
  before use. Verify the IP seen by the login rate limiter in staging.
- Put PostgreSQL on a private interface. Supply `DB_HOST`, `DB_PORT`, `DB_NAME`,
  `DB_USER`, `DB_PASSWORD`, `DB_EXPECTED_NAME`, `APP_ENV=production`,
  `AUTH_COOKIE_MODE=production`, exact HTTPS `AUTH_ALLOWED_ORIGIN`, and a stable,
  random `AUTH_RATE_LIMIT_SECRET` of at least 32 bytes through protected runtime
  configuration. Never put values in Git or logs.
- Explicitly set `SALE_ATTEMPT_PROTOCOL_ENABLED=0` before cutover, then `1` for
  all workers after the migration. The switch is cached per process; restart
  every worker to change it. `/health` checks only process availability; startup
  validates production auth, connected DB identity, and migration revision.

## Preflight and pause

1. Complete staging acceptance with synthetic data, including Owner/Cashier
   authentication, RBAC, Direct/Manual sales, reservation recovery, reports,
   voiding and mobile access. Verify HTTPS cookie, Origin, CSRF and trusted IP.
2. Verify the latest usable encrypted backup and a successful isolated restore.
   Check actual production DB name, schema and Alembic revision; never rely on
   an environment variable alone. Follow `Backup and Restore Runbook.md`,
   including WAL coverage and permanent-fence checks. Record operator, time
   and approved window.
3. Announce sales maintenance. Stop new electronic sale requests at the HTTPS
   entry point; retain the approved paper log and payment evidence. Do not rely
   on disabling a browser button. Drain in-flight requests and DB transactions.
4. Stop **all** legacy application workers and prevent automatic restart.
   Verify none can still accept or later resume a sale POST. Preserve pending
   browser identifiers; do not clear uncertain attempts.

## Migrate and activate

5. Take and verify a pre-migration backup. With all sale writers stopped, apply
   Alembic `20261027_01` to the verified production DB. Confirm the single head,
   `sale_attempts` constraints/indexes, and unchanged historical records.
6. Start only the reviewed release with `APP_ENV=production` and
   `SALE_ATTEMPT_PROTOCOL_ENABLED=1` in every worker. Startup must refuse a
   wrong database or revision. No legacy worker may rejoin this fleet.
7. With authorized staging-style accounts and no real financial test sale,
   confirm login, `/auth/me`, logout, CSRF/Origin rejection, and authenticated
   `/api/v1/sales/capabilities` reporting `reserved_v1` on each worker. Confirm
   the attempt API is gated and the frontend requires reservation before POST.
8. Reopen electronic sales, observe errors, login rate limits, DB connections,
   reservation conflicts and backup health. Record the cutover result.

## Failure response

- Before migration: keep sales paused and restore the known legacy fleet only
  after confirming no reservation-aware workers or open attempts exist.
- After migration or any Reserved/Committed/Cancelled attempt: **do not** switch
  back to legacy writers or downgrade the schema. Keep sales paused, use paper
  logs, investigate exact keys and references, and forward-fix the new release.
  Cancel only through the Owner workflow with external evidence. A cancelled
  physical sale has no electronic replacement workflow yet.
- A missing status at one check does not prove a delayed POST cannot commit.
  Never clear pending browser state or issue a replacement UUID from that alone.
