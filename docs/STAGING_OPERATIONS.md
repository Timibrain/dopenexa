# Staging readiness

Create an empty PostgreSQL database and run `backend/migrations/001_init.sql` through `012_reconciliation.sql` in order. Never clone the development database. Seed only controlled accounts and fixtures after migrations succeed.

Run backups with encrypted storage, daily full snapshots and point-in-time WAL retention appropriate to the environment. A restore test should create a disposable PostgreSQL instance, restore the latest snapshot/WAL, run the migration/schema check, and call `/health` and `/ready`.

Deploy behind Cloudflare HTTPS and a reverse proxy that forwards `X-Request-ID`, `X-Forwarded-Proto`, and `X-Forwarded-For`. Restrict trusted hosts and CORS to the staging/production domains. WebSockets must be proxied with upgrade headers. Add rate limiting at the edge and application boundary before public launch.

Cloudflare staging guidance: create an A/AAAA or CNAME record for the chosen API hostname, enable proxying, use Full (strict) TLS with an origin certificate, enable WebSocket support, apply managed WAF rules, and add moderate per-IP rules for authentication, payments, payouts, refunds, uploads, and admin reconciliation. Do not expose the PostgreSQL or Redis services; the staging compose network is internal and publishes only the API loopback port for the reverse proxy.

Required pre-TestFlight work includes external object storage signing, APNs transport credentials/configuration, monitoring/error reporting, encrypted backups with a tested restore, production secrets, and a clean staging migration run.

## Staging verification

After deploying the revision that includes the verifier, run this from a checkout
linked to Dopenexa's Railway backend service (the environment must be named `staging`):

```sh
railway ssh --environment staging -- python /app/scripts/verify_staging.py --base-url http://127.0.0.1:8000
```

Inside that service container, the equivalent command is:

```sh
python /app/scripts/verify_staging.py --base-url http://127.0.0.1:8000
```

The process inherits the deployed service's existing `DATABASE_URL`, `ENVIRONMENT`,
`STORAGE_BACKEND`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_ENDPOINT`,
`OBJECT_STORAGE_ACCESS_KEY`, `OBJECT_STORAGE_SECRET_KEY`, and
`OBJECT_STORAGE_REGION` (default `auto`). It does not load a local `.env` or import
application startup code. `--base-url` can also be supplied via `STAGING_BASE_URL`;
`--schema` selects an application schema other than the default `public`.

The verifier prints one PASS/FAIL line for readiness, database/migrations, and R2,
and exits 1 if any check fails. It discovers and parses all numbered SQL migrations
and reads PostgreSQL catalogs in a read-only, repeatable-read transaction. It checks
required tables, column types/defaults/nullability, primary/unique/foreign/check
constraints, index definitions/validity, extensions, enum labels, and ledger
functions/triggers. Additional unrelated objects are allowed. It never executes
migration SQL, seed inserts, or backfills, and does not verify historical data.
Unsupported new migration syntax fails closed and requires extending the verifier.
The repository currently applies SQL files directly and has no migration tracker;
PASS reports the latest discovered filename, not a fabricated applied-version row.
A detected standard migration-tracking table fails until its version semantics are
explicitly supported.

R2 verification requires both `ENVIRONMENT=staging` and a successful staging
readiness response. It creates a tiny UUID-named object under
`staging-verification/`, checks an SDK read and an actual HTTP presigned GET, then
deletes and confirms absence in a `finally` block, including after a failed PUT.
The credentials must allow put/get/delete/head on that prefix. Cleanup failures
fail the check. External exception details and SDK logs are suppressed to avoid
exposing credentials, connection strings, or signed URLs. Network calls have
bounded timeouts and retries.

Unit tests run with the normal backend suite. To also run the live schema drift
cases, set `VERIFIER_TEST_DATABASE_URL` to a **disposable migrated test database**
when running `PYTHONPATH=backend pytest -q backend/tests`. These test-only cases
inject schema drift and roll it back; never point that test variable at staging
or production.
