from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .ledger import LedgerLine, post_transaction
from .models import Booking, BookingStatus, Payment, Payout, PayoutReservation, ProfessionalProfile, Refund
from .payment_transitions import PaymentTransitionError, transition_payment


class RefundError(ValueError):
    pass


@dataclass(frozen=True)
class RefundResult:
    refund: Refund
    duplicate: bool = False


async def request_refund(
    session: AsyncSession,
    *,
    payment_id: UUID,
    amount_ngn: int | None,
    idempotency_key: str,
) -> RefundResult:
    if not idempotency_key:
        raise RefundError("Idempotency key is required")
    try:
        payment = await session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
        if not payment:
            raise RefundError("Payment not found")
        existing = await session.scalar(select(Refund).where(
            Refund.payment_id == payment.id, Refund.idempotency_key == idempotency_key
        ).with_for_update())
        if existing:
            await session.commit()
            return RefundResult(existing, duplicate=True)
        if payment.status not in {"paid", "partially_refunded"}:
            raise RefundError("Payment is not eligible for refund")
        pending_total = await session.scalar(select(func.coalesce(func.sum(Refund.amount_ngn), 0)).where(
            Refund.payment_id == payment.id, Refund.status.in_(["pending", "processing"])
        )) or 0
        remaining = payment.amount_ngn - payment.refunded_amount_ngn - int(pending_total)
        requested = remaining if amount_ngn is None else int(amount_ngn)
        if requested <= 0:
            raise RefundError("Refund amount must be greater than zero")
        if requested > remaining:
            raise RefundError("Refund amount exceeds the remaining refundable amount")
        booking = await session.scalar(select(Booking).where(Booking.id == payment.booking_id).with_for_update())
        if not booking:
            raise RefundError("Booking not found")
        # Match payout request serialization so a reservation cannot race this check.
        await session.scalar(select(ProfessionalProfile).where(ProfessionalProfile.id == booking.professional_id).with_for_update())
        active_reservation = await session.scalar(select(PayoutReservation).where(
            PayoutReservation.professional_id == booking.professional_id,
            PayoutReservation.status == "active",
        ).limit(1))
        if active_reservation:
            raise RefundError("Refund is held while a payout reservation is active")
        refund = Refund(payment_id=payment.id, booking_id=booking.id, amount_ngn=requested,
                        idempotency_key=idempotency_key, provider=payment.provider)
        session.add(refund)
        await session.commit()
        await session.refresh(refund)
        return RefundResult(refund)
    except Exception:
        await session.rollback()
        raise


async def process_refund_result(session: AsyncSession, refund_id: UUID, status: str, *, commit: bool = True) -> Refund:
    if status not in {"processing", "succeeded", "failed"}:
        raise RefundError("Status must be processing, succeeded, or failed")
    try:
        refund = await session.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
        if not refund:
            raise RefundError("Refund not found")
        if refund.status in {"succeeded", "failed", "cancelled"}:
            if commit: await session.commit()
            return refund
        if status == "processing":
            refund.status = "processing"
            if commit:
                await session.commit()
                await session.refresh(refund)
            return refund
        if status == "failed":
            refund.status = "failed"
            refund.failure_reason = "Provider rejected refund"
            refund.processed_at = datetime.now(timezone.utc)
            if commit:
                await session.commit()
                await session.refresh(refund)
            return refund

        payment = await session.scalar(select(Payment).where(Payment.id == refund.payment_id).with_for_update())
        booking = await session.scalar(select(Booking).where(Booking.id == refund.booking_id).with_for_update())
        if not payment or not booking or payment.booking_id != booking.id:
            raise RefundError("Refund payment and booking relationship is invalid")
        previous_refunded = payment.refunded_amount_ngn
        new_refunded = previous_refunded + refund.amount_ngn
        if new_refunded > payment.amount_ngn:
            raise RefundError("Refund exceeds the remaining refundable amount")
        # Cumulative integer allocation guarantees that a series of partial
        # refunds sums exactly to the original commission and payable shares.
        commission_before = (previous_refunded * payment.commission_ngn) // payment.amount_ngn
        commission_after = (new_refunded * payment.commission_ngn) // payment.amount_ngn
        commission_reversal = commission_after - commission_before
        payable_reversal = refund.amount_ngn - commission_reversal
        paid_out = await session.scalar(select(Payout.id).where(
            Payout.professional_id == booking.professional_id, Payout.status == "paid"
        ).limit(1))
        payable_account = "professional_receivable" if paid_out else "professional_payable"
        lines = [
            LedgerLine(payable_account, "debit", payable_reversal),
            LedgerLine("processor_cash_clearing", "credit", refund.amount_ngn),
        ]
        if commission_reversal:
            lines.insert(0, LedgerLine("platform_commission", "debit", commission_reversal))
        await post_transaction(
            session,
            idempotency_key=f"refund:{refund.id}:reversal",
            transaction_type="refund_reversal",
            source_type="refund",
            source_id=refund.id,
            lines=lines,
        )
        payment.refunded_amount_ngn = new_refunded
        target_status = "refunded" if new_refunded == payment.amount_ngn else "partially_refunded"
        await transition_payment(session, payment.id, target_status, source="refund", transition_key=f"refund:{refund.id}:status", commit=False)
        refund.status = "succeeded"
        refund.provider_reference = refund.provider_reference or f"mock_refund_{refund.id.hex}"
        refund.processed_at = datetime.now(timezone.utc)
        if target_status == "refunded" and booking.status != BookingStatus.disputed:
            booking.status = BookingStatus.refunded
        if commit:
            await session.commit()
            await session.refresh(refund)
        return refund
    except (PaymentTransitionError, Exception):
        await session.rollback()
        raise


async def mark_refund_submitted(session: AsyncSession, refund_id: UUID, provider_reference: str | None) -> Refund:
    try:
        refund = await session.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
        if not refund:
            raise RefundError("Refund not found")
        if refund.status in {"succeeded", "failed", "cancelled"}:
            return refund
        refund.status = "processing"
        if provider_reference:
            refund.provider_reference = provider_reference
        await session.commit()
        await session.refresh(refund)
        return refund
    except Exception:
        await session.rollback()
        raise
