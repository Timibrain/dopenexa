# Dopenexa Sprint 1 — Customer Vertical Slice

## Definition of done

- Premium Dopenexa visual language implemented in SwiftUI.
- Home experience makes the core action obvious: describe a need.
- Discovery presents professionals as trusted service cards.
- Professional profile works as a mini-business page.
- Service selection exposes price and duration.
- Booking flow captures date/time and shows checkout.
- Confirmation creates a local booking and exposes the project in Bookings.
- Booking-linked chat is represented in Messages.
- FastAPI remains the production integration point.

## Product principle

The UI is intentionally simple: one dominant action per screen, progressive disclosure, strong whitespace, rounded surfaces, clear NGN pricing, and visible trust signals.

## Backend integration remaining for Sprint 1.5

Replace DemoStore actions with API calls for auth, search, professional detail, availability, booking, payment initialization, and messaging. Keep DemoStore as an offline preview mode for design QA.
