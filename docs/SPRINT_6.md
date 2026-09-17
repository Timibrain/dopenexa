# Dopenexa Sprint 6 — Marketplace Experience

Sprint 6 shifts the product from infrastructure-heavy MVP work toward the core marketplace experience.

## Delivered

### Customer experience
- New customer home surface with an AI concierge entry point.
- Upcoming booking/project shortcut.
- Saved professionals shortcut and count.
- Bookings, messages and notifications remain one tap away.
- Trust messaging is visible without adding complexity.

### Discovery
- Real search filters for verification status, minimum rating, maximum service price and service type.
- Filter state is sent to the backend rather than being cosmetic.
- Search results retain the existing professional/profile flow.

### Saved professionals
- Customer-only save/unsave API.
- Persistent saved-professionals table.
- Saved-professionals iOS screen.
- Bookmark action on professional profiles.

### Platform telemetry
- Search event table is ready for product analytics without storing payment/card information.

## API additions

- `GET /saved`
- `POST /saved/{professional_id}`
- `DELETE /saved/{professional_id}`
- `GET /professionals?q=&verified=&min_rating=&max_price_ngn=&service_type=`

## Production boundaries

- Search telemetry currently records the query and result count; a later analytics pipeline should add retention controls and event aggregation.
- Payment provider, APNs, object storage and hosted AI remain configuration-dependent integrations from Sprint 5.
- The app remains Xcode-project agnostic: create an iOS SwiftUI target named `Dopenexa` and add `ios/Dopenexa` sources.
