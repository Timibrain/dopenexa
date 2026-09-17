from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .ledger import LedgerLine, post_transaction
from .models import Payment, PaymentStatusHistory


class PaymentTransitionError(ValueError):
    """Raised when a payment state transition is not allowed."""


ALLOWED_TRANSITIONS = {
    "pending": {"authorized", "paid", "failed", "cancelled"},
    "authorized": {"paid", "failed", "cancelled"},
    "paid": {"partially_refunded", "refunded"},
    "partially_refunded": {"partially_refunded", "refunded"},
}


async def transition_payment(
    session: AsyncSession,
    payment_id: UUID,
    to_status: str,
    *,
    source: str = "system",
    transition_key: str | None = None,
    commit: bool = True,
) -> Payment:
    """Validate and commit one payment transition atomically.

    Capture is the only money movement wired in Phase 1. Refund transitions are
    represented and audited but retain the existing refund implementation until
    the refund-hardening phase adds refund amounts and compensating postings.
    """
    try:
        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if not payment:
            raise PaymentTransitionError("Payment not found")
        if transition_key:
            prior = await session.scalar(
                select(PaymentStatusHistory).where(PaymentStatusHistory.transition_key == transition_key)
            )
            if prior and prior.payment_id == payment.id:
                return payment
        from_status = payment.status
        if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
            raise PaymentTransitionError(f"Invalid payment transition: {from_status} -> {to_status}")

        if to_status == "paid":
            commission = round(payment.amount_ngn * 0.10)
            payable = payment.amount_ngn - commission
            payment.currency = "NGN"
            payment.commission_ngn = commission
            payment.professional_payable_ngn = payable
            payment.captured_at = datetime.now(timezone.utc)
            await post_transaction(
                session,
                idempotency_key=f"payment:{payment.id}:capture",
                transaction_type="payment_capture",
                source_type="payment",
                source_id=payment.id,
                lines=[
                    LedgerLine("processor_cash_clearing", "debit", payment.amount_ngn),
                    LedgerLine("professional_payable", "credit", payable),
                    LedgerLine("platform_commission", "credit", commission),
                ],
            )

        payment.status = to_status
        session.add(PaymentStatusHistory(
            payment_id=payment.id,
            from_status=from_status,
            to_status=to_status,
            source=source,
            transition_key=transition_key,
        ))
        await session.flush()
        if commit:
            await session.commit()
            await session.refresh(payment)
        return payment
    except Exception:
        await session.rollback()
        raise


async def ensure_booking_payment_paid(session: AsyncSession, booking_id: UUID) -> Payment:
    """Guard job start without changing the existing booking status enum."""
    payment = await session.scalar(
        select(Payment).where(Payment.booking_id == booking_id).with_for_update()
    )
    if not payment or payment.status != "paid":
        raise PaymentTransitionError("A captured payment is required before starting this booking")
    return payment
