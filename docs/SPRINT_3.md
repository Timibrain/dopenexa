# Dopenexa Sprint 3

Sprint 3 turns the MVP into an AI-assisted service marketplace experience.

## Included
- `/ai/intent` natural-language intent extraction (deterministic MVP engine).
- `/ai/match` hybrid professional ranking using request/profile/service text plus rating and verification signals.
- AI match result UI with match percentages and match explanations.
- Project workspace attached to every booking.
- Project timeline updates for customers and professionals.
- Notifications API and in-app notification center.
- Booking lifecycle notifications for request, confirmation, decline, start and completion.
- Messaging bubble alignment now uses the authenticated user's UUID.
- Sprint 3 migration for project updates and notifications.

## Honest MVP boundaries
The matching engine is intentionally provider-free and deterministic in this sprint; it is not a hosted LLM or production embedding model. The database already contains pgvector support for a later embedding worker.

Payment remains provider-abstracted. No fake payment success is introduced.

## Run
Apply `backend/migrations/002_sprint3.sql` after the base migration, then run the FastAPI service. The iOS target remains Xcode-project agnostic; add the `ios/Dopenexa` source directory to the Dopenexa SwiftUI target as in the Sprint 2 README.
