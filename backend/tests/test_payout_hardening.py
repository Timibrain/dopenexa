import asyncio
import hashlib
import hmac
import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.ledger import LedgerEntry, LedgerTransaction
from app.models import (
    Booking, BookingStatus, PayoutAccount, PayoutReservation, ProfessionalProfile,
    Role, Service, ServiceType, User, Payment, Payout,
)
from app.payment_transitions import transition_payment
from app.payouts import PayoutError, available_balance, process_provider_result, request_payout
from app.config import settings
from app.webhook_processing import process_paystack_webhook


class PayoutHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await engine.dispose()

    async def _professional_with_balance(self, amount: int = 5000):
        async with SessionLocal() as session:
            customer = User(email=f"payout-customer-{uuid.uuid4()}@example.com", password_hash="x", role=Role.customer, display_name="Customer")
            professional = User(email=f"payout-professional-{uuid.uuid4()}@example.com", password_hash="x", role=Role.professional, display_name="Professional")
            session.add_all([customer, professional]); await session.flush()
            profile = ProfessionalProfile(user_id=professional.id, headline="Payout", bio="Payout", years_experience=1)
            session.add(profile); await session.flush()
            service = Service(professional_id=profile.id, name="Payout service", service_type=ServiceType.fixed, price_ngn=amount, duration_minutes=60)
            session.add(service); await session.flush()
            booking = Booking(customer_id=customer.id, professional_id=profile.id, service_id=service.id, status=BookingStatus.pending,
                              starts_at=datetime.now(timezone.utc) + timedelta(days=2), total_ngn=amount)
            session.add(booking); await session.flush()
            payment = Payment(booking_id=booking.id, provider="pending", status="pending", amount_ngn=amount,
                              idempotency_key=f"payout-payment:{uuid.uuid4()}")
            session.add(payment)
            session.add(PayoutAccount(professional_id=profile.id, provider="dev", account_name="Professional", account_reference="acct"))
            await session.commit()
            payment_id, professional_id = payment.id, profile.id
        async with SessionLocal() as session:
            await transition_payment(session, payment_id, "paid", transition_key=f"payout-capture:{uuid.uuid4()}")
        return professional_id

    async def test_available_balance_and_reservation(self):
        professional_id = await self._professional_with_balance()
        async with SessionLocal() as session:
            self.assertEqual(await available_balance(session, professional_id), 4500)
            result = await request_payout(session, professional_id=professional_id, amount_ngn=3000, idempotency_key=f"key:{uuid.uuid4()}", minimum_ngn=1000)
            self.assertEqual(result.payout.amount_ngn, 3000)
            self.assertEqual(await available_balance(session, professional_id), 1500)
            reservation = await session.scalar(select(PayoutReservation).where(PayoutReservation.payout_id == result.payout.id))
            self.assertEqual((reservation.status, reservation.amount_ngn), ("active", 3000))

    async def test_duplicate_key_returns_same_payout(self):
        professional_id = await self._professional_with_balance()
        key = f"duplicate:{uuid.uuid4()}"
        async with SessionLocal() as session:
            first = await request_payout(session, professional_id=professional_id, amount_ngn=1000, idempotency_key=key, minimum_ngn=1000)
        async with SessionLocal() as session:
            second = await request_payout(session, professional_id=professional_id, amount_ngn=1000, idempotency_key=key, minimum_ngn=1000)
            self.assertTrue(second.duplicate)
            self.assertEqual(first.payout.id, second.payout.id)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Payout).where(Payout.professional_id == professional_id)), 1)

    async def test_concurrent_requests_cannot_spend_same_balance(self):
        professional_id = await self._professional_with_balance()
        async def one(key):
            async with SessionLocal() as session:
                try:
                    result = await request_payout(session, professional_id=professional_id, amount_ngn=3000, idempotency_key=key, minimum_ngn=1000)
                    return result.payout.id
                except PayoutError:
                    return None
        results = await asyncio.gather(one(f"race:{uuid.uuid4()}"), one(f"race:{uuid.uuid4()}"))
        self.assertEqual(sum(x is not None for x in results), 1)
        async with SessionLocal() as session:
            self.assertEqual(await available_balance(session, professional_id), 1500)

    async def test_minimum_and_excess_are_rejected(self):
        professional_id = await self._professional_with_balance()
        async with SessionLocal() as session:
            with self.assertRaises(PayoutError):
                await request_payout(session, professional_id=professional_id, amount_ngn=999, idempotency_key=f"min:{uuid.uuid4()}", minimum_ngn=1000)
            with self.assertRaises(PayoutError):
                await request_payout(session, professional_id=professional_id, amount_ngn=5001, idempotency_key=f"max:{uuid.uuid4()}", minimum_ngn=1000)

    async def test_success_consumes_reservation_once(self):
        professional_id = await self._professional_with_balance()
        async with SessionLocal() as session:
            result = await request_payout(session, professional_id=professional_id, amount_ngn=3000, idempotency_key=f"success:{uuid.uuid4()}", minimum_ngn=1000)
            payout_id = result.payout.id
            await process_provider_result(session, payout_id, "paid")
            await process_provider_result(session, payout_id, "paid")
            reservation = await session.scalar(select(PayoutReservation).where(PayoutReservation.payout_id == payout_id))
            self.assertEqual(reservation.status, "consumed")
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payout_id, LedgerTransaction.transaction_type == "payout_settlement")), 1)

    async def test_failure_releases_reservation_once_and_rolls_back_on_error(self):
        professional_id = await self._professional_with_balance()
        async with SessionLocal() as session:
            result = await request_payout(session, professional_id=professional_id, amount_ngn=3000, idempotency_key=f"failure:{uuid.uuid4()}", minimum_ngn=1000)
            payout_id = result.payout.id
            await process_provider_result(session, payout_id, "failed")
            await process_provider_result(session, payout_id, "failed")
            reservation = await session.scalar(select(PayoutReservation).where(PayoutReservation.payout_id == payout_id))
            self.assertEqual(reservation.status, "released")
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payout_id, LedgerTransaction.transaction_type == "payout_release")), 1)
            self.assertEqual(await available_balance(session, professional_id), 4500)

    async def test_request_rollback_leaves_no_partial_state(self):
        professional_id = await self._professional_with_balance()
        key = f"rollback:{uuid.uuid4()}"
        async with SessionLocal() as session:
            with patch("app.payouts.post_transaction", new=AsyncMock(side_effect=RuntimeError("forced ledger failure"))):
                with self.assertRaises(RuntimeError):
                    await request_payout(session, professional_id=professional_id, amount_ngn=3000, idempotency_key=key, minimum_ngn=1000)
        async with SessionLocal() as session:
            self.assertIsNone(await session.scalar(select(Payout).where(Payout.professional_id == professional_id, Payout.idempotency_key == key)))
            self.assertEqual(await session.scalar(select(func.count()).select_from(PayoutReservation).join(Payout).where(Payout.professional_id == professional_id, Payout.idempotency_key == key)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.idempotency_key == f"payout:{key}:reserve")), 0)

    async def test_paystack_transfer_webhook_consumes_reservation_once(self):
        professional_id = await self._professional_with_balance()
        async with SessionLocal() as session:
            result = await request_payout(session, professional_id=professional_id, amount_ngn=3000, idempotency_key=f"webhook-transfer:{uuid.uuid4()}", minimum_ngn=1000)
            payout = result.payout
            transfer_code = f"TRF_{uuid.uuid4().hex}"; payout.provider = "paystack"; payout.provider_reference = transfer_code; await session.commit()
            body = json.dumps({"event":"transfer.success","data":{"id":f"transfer_evt_{uuid.uuid4().hex}","transfer_code":transfer_code,"reference":payout.dopenexa_reference,"amount":300000,"currency":"NGN","status":"success"}}, separators=(",",":")).encode()
        signature = hmac.new(b"sk_test", body, hashlib.sha512).hexdigest()
        with patch.object(settings, "paystack_secret_key", "sk_test"):
            async with SessionLocal() as session:
                first = await process_paystack_webhook(session, body, signature)
                second = await process_paystack_webhook(session, body, signature)
                self.assertTrue(first.processed); self.assertTrue(second.duplicate)
                reservation = await session.scalar(select(PayoutReservation).where(PayoutReservation.payout_id == payout.id))
                self.assertEqual(reservation.status, "consumed")
                self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payout.id, LedgerTransaction.transaction_type == "payout_settlement")), 1)


if __name__ == "__main__":
    unittest.main()
