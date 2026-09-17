import asyncio
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.ledger import LedgerError, LedgerLine, post_transaction
from app.models import (
    Booking,
    BookingStatus,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    Payment,
    PaymentStatusHistory,
    ProfessionalProfile,
    Role,
    Service,
    ServiceType,
    User,
)
from app.payment_transitions import PaymentTransitionError, transition_payment


class PaymentHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await engine.dispose()

    async def test_balanced_ledger_transaction_succeeds(self):
        async with SessionLocal() as session:
            key = f"test:balanced:{uuid.uuid4()}"
            transaction = await post_transaction(
                session,
                idempotency_key=key,
                transaction_type="test",
                lines=[
                    LedgerLine("processor_cash_clearing", "debit", 5000),
                    LedgerLine("platform_commission", "credit", 5000),
                ],
            )
            await session.commit()
            totals = await session.execute(
                select(LedgerEntry.direction, func.sum(LedgerEntry.amount_ngn))
                .where(LedgerEntry.transaction_id == transaction.id)
                .group_by(LedgerEntry.direction)
            )
            self.assertEqual(dict(totals.all()), {"debit": 5000, "credit": 5000})

    async def test_unbalanced_transaction_is_rejected(self):
        async with SessionLocal() as session:
            key = f"test:unbalanced:{uuid.uuid4()}"
            with self.assertRaises(LedgerError):
                await post_transaction(
                    session,
                    idempotency_key=key,
                    transaction_type="test",
                    lines=[LedgerLine("processor_cash_clearing", "debit", 5000), LedgerLine("platform_commission", "credit", 4999)],
                )
            await session.rollback()
            self.assertIsNone(await session.scalar(select(LedgerTransaction).where(LedgerTransaction.idempotency_key == key)))

    async def test_duplicate_idempotency_key_does_not_duplicate_money(self):
        async with SessionLocal() as session:
            key = f"test:duplicate:{uuid.uuid4()}"
            lines = [LedgerLine("processor_cash_clearing", "debit", 5000), LedgerLine("platform_commission", "credit", 5000)]
            first = await post_transaction(session, idempotency_key=key, transaction_type="test", lines=lines)
            second = await post_transaction(session, idempotency_key=key, transaction_type="test", lines=lines)
            await session.commit()
            self.assertEqual(first.id, second.id)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.idempotency_key == key)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.transaction_id == first.id)), 2)

    async def _payment(self) -> tuple[uuid.UUID, uuid.UUID]:
        async with SessionLocal() as session:
            customer = User(email=f"test-customer-{uuid.uuid4()}@example.com", password_hash="x", role=Role.customer, display_name="Test Customer")
            professional = User(email=f"test-professional-{uuid.uuid4()}@example.com", password_hash="x", role=Role.professional, display_name="Test Professional")
            session.add_all([customer, professional])
            await session.flush()
            profile = ProfessionalProfile(user_id=professional.id, headline="Test", bio="Test", years_experience=1)
            session.add(profile)
            await session.flush()
            service = Service(professional_id=profile.id, name="Test", description="Test", service_type=ServiceType.appointment, price_ngn=5000, duration_minutes=60)
            session.add(service)
            await session.flush()
            booking = Booking(customer_id=customer.id, professional_id=profile.id, service_id=service.id, status=BookingStatus.pending, starts_at=datetime.now(timezone.utc) + timedelta(days=2), ends_at=datetime.now(timezone.utc) + timedelta(days=2, hours=1), total_ngn=5000)
            session.add(booking)
            await session.flush()
            payment = Payment(booking_id=booking.id, provider="pending", status="pending", amount_ngn=5000, idempotency_key=f"test-payment:{uuid.uuid4()}")
            session.add(payment)
            await session.commit()
            return payment.id, booking.id

    async def test_valid_and_invalid_payment_transitions(self):
        payment_id, _ = await self._payment()
        async with SessionLocal() as session:
            await transition_payment(session, payment_id, "authorized", transition_key=f"test-transition:{uuid.uuid4()}")
            payment = await transition_payment(session, payment_id, "paid", transition_key=f"test-transition:{uuid.uuid4()}")
            self.assertEqual(payment.status, "paid")
        async with SessionLocal() as session:
            with self.assertRaises(PaymentTransitionError):
                await transition_payment(session, payment_id, "cancelled")

    async def test_capture_posts_exact_commission_and_payable(self):
        payment_id, _ = await self._payment()
        async with SessionLocal() as session:
            payment = await transition_payment(session, payment_id, "paid", transition_key=f"test-capture:{uuid.uuid4()}")
            self.assertEqual((payment.professional_payable_ngn, payment.commission_ngn), (4500, 500))
            rows = (await session.execute(
                select(LedgerEntry.direction, LedgerEntry.amount_ngn, LedgerAccount.code)
                .join(LedgerAccount, LedgerAccount.id == LedgerEntry.account_id)
                .join(LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id)
                .where(LedgerTransaction.idempotency_key == f"payment:{payment_id}:capture")
            )).all()
            self.assertEqual(sorted((direction, amount, code) for direction, amount, code in rows), sorted([
                ("debit", 5000, "processor_cash_clearing"),
                ("credit", 4500, "professional_payable"),
                ("credit", 500, "platform_commission"),
            ]))

    async def test_transition_rollback_leaves_no_partial_records(self):
        payment_id, _ = await self._payment()
        async with SessionLocal() as session:
            with patch("app.payment_transitions.post_transaction", new=AsyncMock(side_effect=RuntimeError("forced ledger failure"))):
                with self.assertRaises(RuntimeError):
                    await transition_payment(session, payment_id, "paid", transition_key=f"test-rollback:{uuid.uuid4()}")
        async with SessionLocal() as session:
            payment = await session.get(Payment, payment_id)
            self.assertEqual(payment.status, "pending")
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaymentStatusHistory).where(PaymentStatusHistory.payment_id == payment_id)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id == payment_id)), 0)


if __name__ == "__main__":
    unittest.main()
