import unittest
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.models import Booking, BookingStatus, LedgerAccount, LedgerEntry, LedgerTransaction, Payment, PaymentStatusHistory, ProfessionalProfile, Refund, Role, Service, ServiceType, User
from app.payment_transitions import transition_payment
from app.payouts import process_provider_result, request_payout
from app.refunds import RefundError, process_refund_result, request_refund
from app.config import settings
from app.webhook_processing import process_paystack_webhook


class RefundHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await engine.dispose()

    async def _paid_payment(self, booking_status=BookingStatus.pending):
        async with SessionLocal() as session:
            customer = User(email=f"refund-customer-{uuid.uuid4()}@example.com", password_hash="x", role=Role.customer, display_name="Customer")
            professional = User(email=f"refund-professional-{uuid.uuid4()}@example.com", password_hash="x", role=Role.professional, display_name="Professional")
            session.add_all([customer, professional]); await session.flush()
            profile = ProfessionalProfile(user_id=professional.id, headline="Refund", bio="Refund", years_experience=1)
            session.add(profile); await session.flush()
            service = Service(professional_id=profile.id, name="Refund service", service_type=ServiceType.fixed, price_ngn=5000, duration_minutes=60)
            session.add(service); await session.flush()
            booking = Booking(customer_id=customer.id, professional_id=profile.id, service_id=service.id, status=booking_status,
                              starts_at=datetime.now(timezone.utc) + timedelta(days=2), total_ngn=5000)
            session.add(booking); await session.flush()
            payment = Payment(booking_id=booking.id, provider="pending", provider_reference=f"ref_{uuid.uuid4().hex}", status="pending", amount_ngn=5000, currency="NGN", idempotency_key=f"refund-payment:{uuid.uuid4()}")
            session.add(payment); await session.commit()
            payment_id, booking_id, professional_id = payment.id, booking.id, profile.id
        async with SessionLocal() as session:
            await transition_payment(session, payment_id, "paid", transition_key=f"refund-capture:{uuid.uuid4()}")
        return payment_id, booking_id, professional_id

    async def test_partial_refund_exact_reversal_and_status(self):
        payment_id, booking_id, _ = await self._paid_payment()
        async with SessionLocal() as session:
            refund = (await request_refund(session, payment_id=payment_id, amount_ngn=2500, idempotency_key=f"partial:{uuid.uuid4()}" )).refund
            await process_refund_result(session, refund.id, "succeeded")
            payment = await session.get(Payment, payment_id); booking = await session.get(Booking, booking_id)
            self.assertEqual((payment.status, payment.refunded_amount_ngn, booking.status), ("partially_refunded", 2500, BookingStatus.pending))
            rows = (await session.execute(select(LedgerEntry.direction, LedgerEntry.amount_ngn, LedgerAccount.code).join(LedgerAccount).join(LedgerTransaction).where(LedgerTransaction.source_id == refund.id))).all()
            self.assertEqual(sorted(rows), sorted([("debit", 250, "platform_commission"), ("debit", 2250, "professional_payable"), ("credit", 2500, "processor_cash_clearing")]))

    async def test_full_refund_exact_reversal_and_booking_state(self):
        payment_id, booking_id, _ = await self._paid_payment()
        async with SessionLocal() as session:
            refund = (await request_refund(session, payment_id=payment_id, amount_ngn=None, idempotency_key=f"full:{uuid.uuid4()}" )).refund
            await process_refund_result(session, refund.id, "succeeded")
            payment = await session.get(Payment, payment_id); booking = await session.get(Booking, booking_id)
            self.assertEqual((payment.status, payment.refunded_amount_ngn, booking.status), ("refunded", 5000, BookingStatus.refunded))
            rows = (await session.execute(select(LedgerEntry.direction, LedgerEntry.amount_ngn, LedgerAccount.code).join(LedgerAccount).join(LedgerTransaction).where(LedgerTransaction.source_id == refund.id))).all()
            self.assertEqual(sorted(rows), sorted([("debit", 500, "platform_commission"), ("debit", 4500, "professional_payable"), ("credit", 5000, "processor_cash_clearing")]))

    async def test_full_refund_does_not_overwrite_dispute(self):
        payment_id, booking_id, _ = await self._paid_payment(BookingStatus.disputed)
        async with SessionLocal() as session:
            refund = (await request_refund(session, payment_id=payment_id, amount_ngn=None, idempotency_key=f"dispute:{uuid.uuid4()}" )).refund
            await process_refund_result(session, refund.id, "succeeded")
            self.assertEqual((await session.get(Booking, booking_id)).status, BookingStatus.disputed)

    async def test_idempotency_duplicate_and_over_refund_rejected(self):
        payment_id, _, _ = await self._paid_payment()
        key = f"same:{uuid.uuid4()}"
        async with SessionLocal() as session:
            first = (await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=key)).refund
            second = await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=key)
            self.assertTrue(second.duplicate); self.assertEqual(first.id, second.refund.id)
            with self.assertRaises(RefundError):
                await request_refund(session, payment_id=payment_id, amount_ngn=5000, idempotency_key=f"over:{uuid.uuid4()}")
            with self.assertRaises(RefundError):
                await request_refund(session, payment_id=payment_id, amount_ngn=0, idempotency_key=f"zero:{uuid.uuid4()}")

    async def test_duplicate_success_and_failed_refund_are_idempotent(self):
        payment_id, _, _ = await self._paid_payment()
        async with SessionLocal() as session:
            refund = (await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=f"dup:{uuid.uuid4()}" )).refund
            await process_refund_result(session, refund.id, "succeeded"); await process_refund_result(session, refund.id, "succeeded")
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == refund.id)), 1)
            payment = await session.get(Payment, payment_id); self.assertEqual(payment.refunded_amount_ngn, 1000)
        payment_id, _, _ = await self._paid_payment()
        async with SessionLocal() as session:
            refund = (await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=f"fail:{uuid.uuid4()}" )).refund
            await process_refund_result(session, refund.id, "failed"); await process_refund_result(session, refund.id, "failed")
            payment = await session.get(Payment, payment_id); self.assertEqual(payment.refunded_amount_ngn, 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == refund.id)), 0)

    async def test_active_reservation_blocks_refund_and_post_payout_uses_receivable(self):
        payment_id, booking_id, professional_id = await self._paid_payment()
        async with SessionLocal() as session:
            from app.models import PayoutAccount
            session.add(PayoutAccount(professional_id=professional_id, provider="dev", account_name="Professional", account_reference="acct")); await session.commit()
            payout = (await request_payout(session, professional_id=professional_id, amount_ngn=1000, idempotency_key=f"res:{uuid.uuid4()}", minimum_ngn=1000)).payout
            payout_id = payout.id
            with self.assertRaises(RefundError):
                await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=f"blocked:{uuid.uuid4()}")
            await process_provider_result(session, payout_id, "paid")
            refund = (await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=f"after:{uuid.uuid4()}" )).refund
            await process_refund_result(session, refund.id, "succeeded")
            rows = (await session.execute(select(LedgerEntry.direction, LedgerEntry.amount_ngn, LedgerAccount.code).join(LedgerAccount).join(LedgerTransaction).where(LedgerTransaction.source_id == refund.id))).all()
            self.assertIn(("debit", 900, "professional_receivable"), rows)

    async def test_refund_rollback_leaves_financial_state_unchanged(self):
        payment_id, _, _ = await self._paid_payment()
        async with SessionLocal() as session:
            refund = (await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=f"rollback:{uuid.uuid4()}" )).refund
            refund_id = refund.id
            with patch("app.refunds.post_transaction", new=AsyncMock(side_effect=RuntimeError("forced ledger failure"))):
                with self.assertRaises(RuntimeError): await process_refund_result(session, refund.id, "succeeded")
        async with SessionLocal() as session:
            payment = await session.get(Payment, payment_id); refund = await session.get(Refund, refund_id)
            self.assertEqual((payment.refunded_amount_ngn, payment.status, refund.status), (0, "paid", "pending"))
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == refund.id)), 0)

    async def test_paystack_partial_then_full_refund_webhooks_are_idempotent(self):
        payment_id, booking_id, _ = await self._paid_payment()
        with patch.object(settings, "paystack_secret_key", "sk_test"):
            async with SessionLocal() as session:
                first = (await request_refund(session, payment_id=payment_id, amount_ngn=1000, idempotency_key=f"ps-partial:{uuid.uuid4()}" )).refund
                partial_reference = f"RF_partial_{uuid.uuid4().hex}"; first.provider_reference = partial_reference; first.status = "processing"; await session.commit()
                body = json.dumps({"event":"refund.processed","data":{"id":"RF_partial_event","transaction":"ref_missing","amount":100000,"currency":"NGN","status":"processed"}},separators=(",",":")).encode()
                # Match the refund through provider reference.
                payload=json.loads(body); payload["data"]["id"]=partial_reference; body=json.dumps(payload,separators=(",",":")).encode(); sig=hmac.new(b"sk_test",body,hashlib.sha512).hexdigest()
                await process_paystack_webhook(session, body, sig); await process_paystack_webhook(session, body, sig)
                payment = await session.get(Payment, payment_id); self.assertEqual((payment.status,payment.refunded_amount_ngn), ("partially_refunded",1000))
                second = (await request_refund(session, payment_id=payment_id, amount_ngn=4000, idempotency_key=f"ps-full:{uuid.uuid4()}" )).refund
                full_reference = f"RF_full_{uuid.uuid4().hex}"; second.provider_reference = full_reference; second.status = "processing"; await session.commit()
                body2=json.dumps({"event":"refund.processed","data":{"id":full_reference,"transaction":"ref_missing","amount":400000,"currency":"NGN","status":"processed"}},separators=(",",":")).encode(); sig2=hmac.new(b"sk_test",body2,hashlib.sha512).hexdigest()
                await process_paystack_webhook(session, body2, sig2)
                payment = await session.get(Payment, payment_id); booking = await session.get(Booking, booking_id)
                self.assertEqual((payment.status,payment.refunded_amount_ngn,booking.status), ("refunded",5000,BookingStatus.refunded))
                self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_type == "refund", LedgerTransaction.source_id.in_(select(Refund.id).where(Refund.payment_id == payment_id)))), 2)


if __name__ == "__main__": unittest.main()
