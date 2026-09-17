import asyncio
import hashlib
import hmac
import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, engine
from app.ledger import LedgerEntry
from app.models import (
    Booking,
    BookingStatus,
    LedgerTransaction,
    Payment,
    PaymentStatusHistory,
    ProfessionalProfile,
    Role,
    Service,
    ServiceType,
    User,
    PaymentEvent,
)
from app.payment_transitions import PaymentTransitionError, ensure_booking_payment_paid
from app.webhook_processing import WebhookProcessingError, process_webhook


def signed(body: bytes) -> str:
    return hmac.new(settings.payment_webhook_secret.encode(), body, hashlib.sha256).hexdigest()


class WebhookProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await engine.dispose()

    async def _payment(self, *, status: str = "pending", booking_status: BookingStatus = BookingStatus.pending):
        async with SessionLocal() as session:
            customer = User(email=f"webhook-customer-{uuid.uuid4()}@example.com", password_hash="x", role=Role.customer, display_name="Webhook Customer")
            professional = User(email=f"webhook-professional-{uuid.uuid4()}@example.com", password_hash="x", role=Role.professional, display_name="Webhook Professional")
            session.add_all([customer, professional])
            await session.flush()
            profile = ProfessionalProfile(user_id=professional.id, headline="Webhook", bio="Webhook", years_experience=1)
            session.add(profile)
            await session.flush()
            service = Service(professional_id=profile.id, name="Webhook service", description="Webhook", service_type=ServiceType.appointment, price_ngn=5000, duration_minutes=60)
            session.add(service)
            await session.flush()
            booking = Booking(customer_id=customer.id, professional_id=profile.id, service_id=service.id, status=booking_status, starts_at=datetime.now(timezone.utc) + timedelta(days=3), ends_at=datetime.now(timezone.utc) + timedelta(days=3, hours=1), total_ngn=5000)
            session.add(booking)
            await session.flush()
            payment = Payment(booking_id=booking.id, provider="pending", provider_reference=f"ref_{uuid.uuid4().hex}", status=status, amount_ngn=5000, currency="NGN", idempotency_key=f"webhook-payment:{uuid.uuid4()}")
            session.add(payment)
            await session.commit()
            return payment.id, payment.provider_reference, booking.id

    @staticmethod
    def _body(reference: str, event_id: str | None = None, **overrides) -> bytes:
        data = {
            "provider": "pending",
            "event_id": event_id or f"evt_{uuid.uuid4().hex}",
            "event_type": "payment.succeeded",
            "reference": reference,
            "amount": 5000,
            "currency": "NGN",
            "status": "success",
        }
        data.update(overrides)
        return json.dumps(data).encode()

    async def test_valid_paid_webhook_posts_capture_once(self):
        payment_id, reference, _ = await self._payment()
        body = self._body(reference)
        async with SessionLocal() as session:
            result = await process_webhook(session, body, signed(body))
            self.assertTrue(result.processed)
        async with SessionLocal() as session:
            payment = await session.get(Payment, payment_id)
            self.assertEqual(payment.status, "paid")
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaymentStatusHistory).where(PaymentStatusHistory.payment_id == payment_id)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerEntry).join(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 3)

    async def test_duplicate_webhook_is_safe(self):
        payment_id, reference, _ = await self._payment()
        body = self._body(reference, f"evt_duplicate_{uuid.uuid4().hex}")
        async with SessionLocal() as session:
            await process_webhook(session, body, signed(body))
        async with SessionLocal() as session:
            result = await process_webhook(session, body, signed(body))
            self.assertTrue(result.duplicate)
        async with SessionLocal() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaymentStatusHistory).where(PaymentStatusHistory.payment_id == payment_id)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 1)

    async def test_concurrent_duplicate_webhooks_are_safe(self):
        payment_id, reference, _ = await self._payment()
        body = self._body(reference, f"evt_concurrent_{uuid.uuid4().hex}")

        async def deliver():
            async with SessionLocal() as session:
                return await process_webhook(session, body, signed(body))

        results = await asyncio.gather(deliver(), deliver())
        self.assertEqual(sum(result.processed for result in results), 1)
        self.assertEqual(sum(result.duplicate for result in results), 1)
        async with SessionLocal() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaymentStatusHistory).where(PaymentStatusHistory.payment_id == payment_id)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 1)

    async def test_invalid_signature_is_rejected_without_event(self):
        _, reference, _ = await self._payment()
        event_id = f"evt_invalid_signature_{uuid.uuid4().hex}"
        body = self._body(reference, event_id)
        async with SessionLocal() as session:
            with self.assertRaisesRegex(WebhookProcessingError, "Invalid webhook signature"):
                await process_webhook(session, body, "wrong")
            self.assertIsNone(await session.scalar(select(PaymentEvent).where(PaymentEvent.provider == "pending", PaymentEvent.event_id == event_id)))

    async def test_mismatched_events_fail_without_financial_changes(self):
        cases = [
            {"amount": 4999},
            {"currency": "USD"},
            {"reference": "wrong-reference"},
        ]
        for override in cases:
            payment_id, reference, _ = await self._payment()
            body_reference = override.get("reference", reference)
            body_overrides = {key: value for key, value in override.items() if key != "reference"}
            body = self._body(body_reference, **body_overrides)
            async with SessionLocal() as session:
                with self.assertRaises(WebhookProcessingError):
                    await process_webhook(session, body, signed(body))
            async with SessionLocal() as session:
                payment = await session.get(Payment, payment_id)
                self.assertEqual(payment.status, "pending")
                self.assertEqual(await session.scalar(select(func.count()).select_from(PaymentStatusHistory).where(PaymentStatusHistory.payment_id == payment_id)), 0)
                self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 0)

    async def test_invalid_transition_is_recorded_without_capture(self):
        payment_id, reference, _ = await self._payment(status="failed")
        body = self._body(reference)
        async with SessionLocal() as session:
            with self.assertRaises(WebhookProcessingError):
                await process_webhook(session, body, signed(body))
        async with SessionLocal() as session:
            event = await session.scalar(select(PaymentEvent).where(PaymentEvent.payload["reference"].astext == reference))
            self.assertEqual(event.processing_status, "failed")
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 0)

    async def test_transition_failure_rolls_back_financial_changes(self):
        payment_id, reference, _ = await self._payment()
        body = self._body(reference)
        with patch("app.payment_transitions.post_transaction", new=AsyncMock(side_effect=RuntimeError("forced failure"))):
            async with SessionLocal() as session:
                with self.assertRaises(RuntimeError):
                    await process_webhook(session, body, signed(body))
        async with SessionLocal() as session:
            payment = await session.get(Payment, payment_id)
            self.assertEqual(payment.status, "pending")
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaymentStatusHistory).where(PaymentStatusHistory.payment_id == payment_id)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 0)

    async def test_booking_start_requires_paid_payment(self):
        payment_id, _, booking_id = await self._payment(booking_status=BookingStatus.confirmed)
        async with SessionLocal() as session:
            with self.assertRaises(PaymentTransitionError):
                await ensure_booking_payment_paid(session, booking_id)
            payment = await session.get(Payment, payment_id)
            payment.status = "paid"
            await session.commit()
        async with SessionLocal() as session:
            paid = await ensure_booking_payment_paid(session, booking_id)
            self.assertEqual(paid.status, "paid")
            await session.rollback()


if __name__ == "__main__":
    unittest.main()
