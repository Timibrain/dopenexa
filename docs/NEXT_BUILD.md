# Next Build: production hardening

The repository is intentionally an MVP foundation, not a production launch.

Before real money or public launch:

- Replace dev JWT secret with managed secrets.
- Implement refresh-token rotation/revocation storage.
- Add password reset and email/phone verification.
- Add database migration tooling (Alembic).
- Add PostgreSQL exclusion constraint for booking time overlap.
- Add transactional outbox for notifications.
- Add Redis rate limiting.
- Add WebSocket realtime messaging.
- Integrate a real NGN payment provider and verify its exact webhook scheme.
- Add financial ledger entries for every money movement.
- Add refund/dispute state machine.
- Add professional verification workflow.
- Add admin authorization and audit tooling.
- Add object storage for attachments.
- Add observability, tests and CI.
- Add AI intent extraction + embeddings + pgvector ranking after deterministic search works.
- Add staging before production.
