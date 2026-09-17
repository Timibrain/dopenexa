from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .ledger import LedgerLine, post_transaction
from .models import Booking, LedgerAccount, LedgerEntry, LedgerTransaction, Payment, Payout, PayoutAccount, PayoutReservation, ProfessionalProfile


class PayoutError(ValueError):
    pass


@dataclass(frozen=True)
class PayoutResult:
    payout: Payout
    duplicate: bool = False


async def _ledger_balance(session: AsyncSession, professional_id: UUID) -> int:
    """Credit balance of the professional payable account, before reservations."""
    accounts = (await session.scalars(select(LedgerAccount).where(LedgerAccount.code.in_(["professional_payable", "professional_payable_reserved"])))).all()
    if not accounts:
        return 0
    source_scope = or_(
        and_(LedgerTransaction.source_type == "payment", Payment.booking_id == Booking.id, Booking.professional_id == professional_id),
        and_(LedgerTransaction.source_type == "payout", Payout.professional_id == professional_id),
    )
    base = select(func.coalesce(func.sum(LedgerEntry.amount_ngn), 0)).select_from(LedgerEntry).join(
        LedgerTransaction, LedgerTransaction.id == LedgerEntry.transaction_id
    ).outerjoin(Payment, and_(LedgerTransaction.source_type == "payment", LedgerTransaction.source_id == Payment.id)).outerjoin(
        Booking, and_(Payment.booking_id == Booking.id)
    ).outerjoin(Payout, and_(LedgerTransaction.source_type == "payout", LedgerTransaction.source_id == Payout.id)
    ).where(LedgerEntry.account_id.in_([a.id for a in accounts]), source_scope)
    credit = await session.scalar(base.where(LedgerEntry.direction == "credit")) or 0
    debit = await session.scalar(base.where(LedgerEntry.direction == "debit")) or 0
    return int(credit) - int(debit)


async def available_balance(session: AsyncSession, professional_id: UUID, *, lock: bool = False) -> int:
    query = select(func.coalesce(func.sum(PayoutReservation.amount_ngn), 0)).where(
        PayoutReservation.professional_id == professional_id,
        PayoutReservation.status == "active",
    )
    # The professional profile row is locked by request_payout before this
    # aggregate is read; PostgreSQL does not allow FOR UPDATE on aggregates.
    reserved = await session.scalar(query) or 0
    return max(0, await _ledger_balance(session, professional_id) - int(reserved))


async def request_payout(
    session: AsyncSession,
    *,
    professional_id: UUID,
    amount_ngn: int | None,
    idempotency_key: str,
    minimum_ngn: int,
) -> PayoutResult:
    if not idempotency_key:
        raise PayoutError("Idempotency key is required")
    try:
        # The profile row is the per-professional serialization lock.
        professional = await session.scalar(select(ProfessionalProfile).where(ProfessionalProfile.id == professional_id).with_for_update())
        if not professional:
            raise PayoutError("Professional profile not found")
        existing = await session.scalar(select(Payout).where(
            Payout.professional_id == professional_id, Payout.idempotency_key == idempotency_key
        ).with_for_update())
        if existing:
            await session.commit()
            return PayoutResult(existing, duplicate=True)
        balance = await available_balance(session, professional_id, lock=True)
        requested = balance if amount_ngn is None else int(amount_ngn)
        if requested < minimum_ngn:
            raise PayoutError(f"Minimum payout is ₦{minimum_ngn:,}")
        if requested > balance:
            raise PayoutError("Requested payout exceeds available balance")
        account = await session.scalar(select(PayoutAccount).where(
            PayoutAccount.professional_id == professional_id, PayoutAccount.is_default.is_(True)
        ))
        if not account:
            raise PayoutError("Add a payout account first")
        payout = Payout(professional_id=professional_id, amount_ngn=requested, provider=account.provider,
                        status="pending", idempotency_key=idempotency_key,
                        dopenexa_reference=f"dpx_payout_{uuid4().hex}")
        session.add(payout)
        await session.flush()
        reservation = PayoutReservation(payout_id=payout.id, professional_id=professional_id, amount_ngn=requested)
        session.add(reservation)
        await session.flush()
        await post_transaction(session, idempotency_key=f"payout:{payout.id}:reserve", transaction_type="payout_reservation",
            source_type="payout", source_id=payout.id,
            lines=[LedgerLine("professional_payable", "debit", requested), LedgerLine("professional_payable_reserved", "credit", requested)])
        await session.commit()
        await session.refresh(payout)
        return PayoutResult(payout)
    except Exception:
        await session.rollback()
        raise


async def process_provider_result(session: AsyncSession, payout_id: UUID, status: str, *, commit: bool = True) -> Payout:
    if status not in {"paid", "failed"}:
        raise PayoutError("Status must be paid or failed")
    try:
        payout = await session.scalar(select(Payout).where(Payout.id == payout_id).with_for_update())
        if not payout:
            raise PayoutError("Payout not found")
        reservation = await session.scalar(select(PayoutReservation).where(PayoutReservation.payout_id == payout.id).with_for_update())
        if payout.status == status and (reservation is None or reservation.status in {"consumed", "released"}):
            if commit: await session.commit()
            return payout
        if not reservation or reservation.status != "active":
            raise PayoutError("Payout reservation is not active")
        if status == "paid":
            await post_transaction(session, idempotency_key=f"payout:{payout.id}:settle", transaction_type="payout_settlement",
                source_type="payout", source_id=payout.id,
                lines=[LedgerLine("professional_payable_reserved", "debit", payout.amount_ngn), LedgerLine("processor_cash_clearing", "credit", payout.amount_ngn)])
            reservation.status = "consumed"
            reservation.released_at = datetime.now(timezone.utc)
            payout.status = "paid"
            payout.paid_at = datetime.now(timezone.utc)
            payout.failure_reason = None
        else:
            await post_transaction(session, idempotency_key=f"payout:{payout.id}:release", transaction_type="payout_release",
                source_type="payout", source_id=payout.id,
                lines=[LedgerLine("professional_payable_reserved", "debit", payout.amount_ngn), LedgerLine("professional_payable", "credit", payout.amount_ngn)])
            reservation.status = "released"
            reservation.released_at = datetime.now(timezone.utc)
            payout.status = "failed"
            payout.paid_at = None
            payout.failure_reason = "Provider rejected payout"
        if commit:
            await session.commit()
            await session.refresh(payout)
        return payout
    except Exception:
        await session.rollback()
        raise


async def mark_transfer_initialized(session: AsyncSession, payout_id: UUID, transfer_code: str, *, commit: bool = True) -> Payout:
    try:
        payout = await session.scalar(select(Payout).where(Payout.id == payout_id).with_for_update())
        if not payout:
            raise PayoutError("Payout not found")
        if payout.status in {"paid", "failed"}:
            return payout
        payout.provider_reference = transfer_code
        payout.status = "processing"
        if commit:
            await session.commit(); await session.refresh(payout)
        else:
            await session.flush()
        return payout
    except Exception:
        await session.rollback()
        raise
