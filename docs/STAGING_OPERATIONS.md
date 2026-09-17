# Staging readiness

Create an empty PostgreSQL database and run `backend/migrations/001_init.sql` through `012_reconciliation.sql` in order. Never clone the development database. Seed only controlled accounts and fixtures after migrations succeed.

Run backups with encrypted storage, daily full snapshots and point-in-time WAL retention appropriate to the environment. A restore test should create a disposable PostgreSQL instance, restore the latest snapshot/WAL, run the migration/schema check, and call `/health` and `/ready`.

Deploy behind Cloudflare HTTPS and a reverse proxy that forwards `X-Request-ID`, `X-Forwarded-Proto`, and `X-Forwarded-For`. Restrict trusted hosts and CORS to the staging/production domains. WebSockets must be proxied with upgrade headers. Add rate limiting at the edge and application boundary before public launch.

Cloudflare staging guidance: create an A/AAAA or CNAME record for the chosen API hostname, enable proxying, use Full (strict) TLS with an origin certificate, enable WebSocket support, apply managed WAF rules, and add moderate per-IP rules for authentication, payments, payouts, refunds, uploads, and admin reconciliation. Do not expose the PostgreSQL or Redis services; the staging compose network is internal and publishes only the API loopback port for the reverse proxy.

Required pre-TestFlight work includes external object storage signing, APNs transport credentials/configuration, monitoring/error reporting, encrypted backups with a tested restore, production secrets, and a clean staging migration run.
