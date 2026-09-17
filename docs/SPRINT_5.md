# Sprint 5 — Production foundation

Sprint 5 hardens the marketplace without pretending external infrastructure is live when credentials/certificates are absent.

## Included

### Authentication
- Refresh tokens are persisted as revocable sessions.
- Refresh rotation revokes the previous session.
- Logout revokes the refresh session.

### AI
- Configurable OpenAI-compatible provider for intent extraction and 1536-dimensional embeddings.
- `/ai/reindex` builds/refreshes professional embeddings when an AI key is configured.
- `/ai/match` uses semantic vector search when configured and a deterministic pgvector fallback otherwise.
- No API key is bundled.

### Trust
- Professional verification submissions.
- Professional verification history.
- Admin verification queue and approve/reject action.
- Customer-facing verified state remains derived from the reviewed profile status.

### Money movement
- Payout account storage.
- Available earnings calculation.
- Payout request creation with a minimum threshold.
- Payout status/history model.
- Development-only admin simulation endpoint; production settlement should come from a signed provider webhook.
- Payment webhook events are idempotent through `payment_events`.

### Notifications
- Device-token registration API for iOS push-token handoff.
- Existing in-app notifications remain available.

## Production boundaries

The repository does **not** ship secrets, bank credentials, APNs certificates, or a claim that money has been collected. Configure a real payment/payout provider and push infrastructure in staging before enabling those paths in production.

## New environment variables

- `AI_PROVIDER=deterministic` or `openai`
- `AI_API_KEY=`
- `AI_BASE_URL=https://api.openai.com/v1`
- `AI_EMBEDDING_MODEL=text-embedding-3-small`
- `AI_CHAT_MODEL=gpt-4o-mini`
- `STORAGE_BACKEND=local`
- `UPLOAD_DIR=uploads`
- `MINIMUM_PAYOUT_NGN=1000`

## New endpoints

- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /ai/reindex`
- `POST /trust/verification`
- `GET /trust/verification/me`
- `GET /trust/admin/verification`
- `POST /trust/admin/verification/{submission_id}`
- `POST /devices/register`
- `DELETE /devices/{device_id}`
- `PUT /payouts/account`
- `GET /payouts/balance`
- `GET /payouts`
- `POST /payouts`

## iOS

- Persistent refresh-token storage.
- Server-side logout.
- Trust & verification screen.
- Earnings & payouts screen.
- Payout account and payout request UI.

The iOS project remains Xcode-project agnostic; add the source directory to a SwiftUI App target named `Dopenexa` as in earlier sprints.
