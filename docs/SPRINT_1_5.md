# Sprint 1.5 — Live data integration

Sprint 1.5 converts the Sprint 1 UI from demo data to API-backed flows.

## Connected

- Account registration/login with JWT
- Persistent auth token on iOS
- Live professional search
- Live professional profiles and services
- Live availability slots from the professional schedule
- Booking creation with overlap protection
- Booking list from the API
- Booking-linked conversation creation
- Conversation list and message retrieval
- Sending messages through the API
- Payment session creation boundary
- Signed webhook boundary
- Sign out

## Payment boundary

No real provider credentials are bundled. `PendingProvider` is an explicit adapter boundary. Configure the selected NGN provider only after staging credentials, exact webhook verification, idempotency, refunds and ledger handling are implemented.

## Local setup

```bash
docker compose up --build
```

Then open `http://localhost:8000/docs`.

For the iOS simulator, `http://localhost:8000` works. For a physical device, change `dopenexa_api_url` or `APIClient.baseURL` to the Mac's LAN IP / staging HTTPS URL.

## Seed a professional

The next production step is an admin/professional onboarding UI. For local development, create a professional with the API, then create its profile/service/availability. See `docs/API_EXAMPLES.md`.
