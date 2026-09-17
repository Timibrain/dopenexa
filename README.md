# Dopenexa MVP

Dopenexa is a Naira-first professional-services marketplace.

This repository implements the first vertical slice:

Customer:
Home → search/describe need → professional results → professional profile → service → availability → booking → payment session → confirmation → booking-linked messaging → review.

Professional:
Create profile → publish service → set availability → receive booking → mark complete.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL/PostGIS, pgvector, Redis
- Auth: JWT access/refresh tokens, bcrypt password hashing
- Mobile: SwiftUI, async/await, URLSession
- Local infrastructure: Docker Compose

## Important

Payment integration is deliberately provider-neutral. The API creates a payment session and exposes a signed webhook endpoint. Connect a real NGN provider only after configuring its credentials and webhook signature verification.

The mobile app uses a small API client and can point at a local or staging API.

## Run backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or:

```bash
docker compose up --build
```

API docs:
http://localhost:8000/docs

Health:
http://localhost:8000/health

## Run iOS

Open the `ios/Dopenexa` source in an Xcode SwiftUI App project named `Dopenexa`, or copy the source directory into an existing SwiftUI project.

Set the API base URL in `Core/APIClient.swift`.

For a physical iPhone, do not use localhost; use the Mac's LAN IP or a staging HTTPS endpoint.

## MVP API

- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- GET /professionals
- GET /professionals/{id}
- POST /professionals/me
- POST /professionals/me/services
- POST /professionals/me/availability
- GET /services/{id}
- POST /availability/check
- POST /bookings
- GET /bookings
- GET /bookings/{id}
- POST /bookings/{id}/cancel
- POST /bookings/{id}/complete
- POST /payments/create
- POST /payments/webhooks
- GET /conversations
- GET /conversations/{id}/messages
- POST /conversations/{id}/messages
- POST /reviews

## Development order

1. Start PostgreSQL + Redis.
2. Start FastAPI.
3. Register a customer and professional.
4. Create a professional profile/service/availability.
5. Search and book.
6. Connect a real payment provider in staging.
7. Add the AI intent/ranking layer.

## Sprint 2
See `docs/SPRINT_2.md` for the professional workspace implementation and current boundaries.


## Sprint 3
See `docs/SPRINT_3.md` for AI matching, project workspace and notifications.

## Sprint 4
Trust and collaboration layer added: pgvector hybrid matching, reviews, attachments, disputes, payment lifecycle/webhook handling, and richer iOS project workflows. See `docs/SPRINT_4.md`.

## Sprint 5
Production foundation added: revocable refresh sessions, configurable LLM/embedding provider, verification workflow, payout accounts/balance/history, payout requests, idempotent payment events, device-token registration, and professional trust/earnings UI. See `docs/SPRINT_5.md`.

## Sprint 6
Marketplace experience added: customer concierge home, real discovery filters, saved professionals, profile bookmarks, and search-event infrastructure. See `docs/SPRINT_6.md`.
