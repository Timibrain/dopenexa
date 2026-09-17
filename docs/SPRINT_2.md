# Dopenexa Sprint 2 — Professional Workspace

Sprint 2 turns the professional side of Dopenexa into a usable operating workspace while preserving the customer booking flow.

## Implemented
- Professional profile onboarding and service-area field.
- Professional dashboard metrics: pending requests, upcoming bookings, in-progress work, completed jobs, earnings, rating.
- Incoming booking requests with accept/decline actions.
- Booking lifecycle endpoints for confirm, decline and start.
- Professional service CRUD surface (create/edit/deactivate API; create UI in the workspace).
- Weekly availability management with add/delete UI and API.
- Current-user endpoint and role-aware iOS navigation.
- Professional workspace tab replaces customer Home/Discover for professional accounts.
- Database additions for professional onboarding/service-area and service creation timestamp.

## Deliberate boundaries
- Payment provider remains a pending adapter; Sprint 2 does not claim real funds are collected.
- AI semantic matching/pgvector ranking is not yet production-integrated.
- Notifications are represented by existing app surfaces but push delivery is not implemented here.
- Attachments/project files and agency workspace remain future work.

## Validation
- Python backend compiled with `python -m compileall -q backend/app`.
- Swift sources validated with `swiftc -parse` where Swift toolchain is available.
