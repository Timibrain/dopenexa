# Dopenexa Sprint 7

Sprint 7 turns the marketplace foundation into a more connected, personalized product experience.

## Delivered
- Personalized recommendation endpoint with deterministic trust/activity signals.
- Customer home redesign centered on the AI concierge.
- Recommendation strip and saved-professional shortcuts.
- Real-time conversation transport over authenticated WebSockets.
- Message persistence + broadcast to conversation members.
- Message notifications for the receiving participant.
- Correct sender identity in standard message responses.
- iOS real-time project chat with automatic message updates.
- Public professional profile review section.
- Existing booking, project, trust, payout, attachment and payment boundaries retained.

## Production boundaries
- Recommendation ranking is deterministic MVP logic, not a trained recommender model.
- WebSocket authentication uses the access token as a query parameter; production should prefer a short-lived socket token to avoid token exposure in URL logs.
- Push delivery still requires APNs infrastructure from Sprint 5.
- Payment and payout providers remain adapter-based until production credentials and provider contracts are supplied.
