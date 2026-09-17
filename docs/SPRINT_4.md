# Dopenexa Sprint 4

Sprint 4 hardens the marketplace around trust, collaboration and transaction lifecycle.

## Delivered
- pgvector-backed 64-dimensional semantic profile embeddings with hybrid lexical/trust ranking.
- Professional reviews retrieval and customer review submission from completed bookings.
- Project file attachments: authenticated upload/list/download, 10 MB limit, safe MIME allowlist.
- Disputes with authenticated booking ownership, status and reason/details.
- Payment status endpoint, refund workflow boundary, signed webhook parsing and payment-state transitions.
- Payment success webhook can mark a pending booking confirmed; failures are recorded as failed.
- iOS project workspace now exposes file sharing, reviews and issue reporting.

## Important production boundaries
The bundled payment adapter remains a safe `PendingProvider`; it does not pretend to charge cards. Configure a real NGN provider adapter and its secrets before production. Uploaded files currently use local container storage; production should move storage to an object store with signed URLs and malware scanning. The embedding generator is deterministic and local so the project remains runnable without third-party AI credentials; it is an embedding-compatible foundation, not a hosted LLM.
