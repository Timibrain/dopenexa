"""Provider reconciliation and read-only financial consistency checks.

All state changes are delegated to the existing transition/settlement services;
this module only coordinates verification, auditing, and retry-safe commits.
"""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import (
    Booking, LedgerAccount, LedgerEntry, LedgerTransaction, Payment,
    Payout, PayoutReservation, ReconciliationRun, Refund,
)
from .payment_provider import PaystackProvider, ProviderError, configured_payment_provider
from .payment_transitions import PaymentTransitionError, transition_payment
from .payouts import PayoutError, process_provider_result
from .refunds import RefundError, process_refund_result


class ReconciliationError(ValueError):
    pass


def _provider() -> PaystackProvider:
    provider = configured_payment_provider()
    if not isinstance(provider, PaystackProvider):
        raise ReconciliationError("Provider verification is unavailable for the configured provider")
    return provider


async def _audit(session: AsyncSession, *, entity_type: str, entity_id: UUID, provider: str,
                 previous_state: str | None, provider_state: str | None, resulting_state: str | None,
                 action: str, success: bool, error_message: str | None = None) -> ReconciliationRun:
    item = ReconciliationRun(entity_type=entity_type, entity_id=entity_id, provider=provider,
                             previous_state=previous_state, provider_state=provider_state,
                             resulting_state=resulting_state, action=action, success=success,
                             error_message=error_message[:2000] if error_message else None)
    session.add(item)
    await session.flush()
    return item


async def _failure_audit(session: AsyncSession, entity_type: str, entity_id: UUID, provider: str,
                         previous: str | None, action: str, exc: Exception) -> None:
    await session.rollback()
    await _audit(session, entity_type=entity_type, entity_id=entity_id, provider=provider,
                 previous_state=previous, provider_state=None, resulting_state=previous,
                 action=action, success=False, error_message=str(exc))
    await session.commit()


async def reconcile_payment(session: AsyncSession, payment_id: UUID) -> dict[str, Any]:
    payment = await session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if not payment:
        raise ReconciliationError("Payment not found")
    previous = payment.status
    try:
        provider = _provider()
        if payment.provider != provider.provider_name or not payment.provider_reference:
            raise ReconciliationError("Payment has no verifiable Paystack reference")
        result = await provider.verify_transaction(payment.provider_reference)
        if result.currency != "NGN" or result.amount_ngn != payment.amount_ngn:
            raise ReconciliationError("Provider payment amount or currency does not match")
        action = "already_correct"
        if result.status == "paid" and payment.status in {"pending", "authorized"}:
            await transition_payment(session, payment.id, "paid", source="reconciliation",
                                     transition_key=f"reconcile:payment:{payment.id}:paid", commit=False)
            action = "transitioned_paid"
        elif result.status == "failed" and payment.status in {"pending", "authorized"}:
            await transition_payment(session, payment.id, "failed", source="reconciliation",
                                     transition_key=f"reconcile:payment:{payment.id}:failed", commit=False)
            action = "transitioned_failed"
        elif result.status in {"pending", "reversed", "unknown"}:
            action = "remains_pending" if result.status == "pending" else "provider_state_requires_review"
        elif result.status != payment.status:
            action = "provider_local_mismatch"
        await _audit(session, entity_type="payment", entity_id=payment.id, provider=result.provider,
                     previous_state=previous, provider_state=result.status, resulting_state=payment.status,
                     action=action, success=True)
        await session.commit()
        return {"entity_type": "payment", "id": str(payment.id), "previous_state": previous,
                "provider_state": result.status, "resulting_state": payment.status, "action": action}
    except Exception as exc:
        await _failure_audit(session, "payment", payment.id, payment.provider, previous, "reconciliation_failed", exc)
        raise


async def reconcile_payout(session: AsyncSession, payout_id: UUID) -> dict[str, Any]:
    payout = await session.scalar(select(Payout).where(Payout.id == payout_id).with_for_update())
    if not payout:
        raise ReconciliationError("Payout not found")
    previous = payout.status
    try:
        provider = _provider()
        if payout.provider != provider.provider_name or not payout.provider_reference:
            raise ReconciliationError("Payout has no verifiable provider transfer reference")
        result = await provider.verify_transfer(payout.provider_reference)
        if result.currency != "NGN" or result.amount_ngn != payout.amount_ngn:
            raise ReconciliationError("Provider payout amount or currency does not match")
        action = "already_correct"
        if result.status in {"success", "successful"} and payout.status != "paid":
            await process_provider_result(session, payout.id, "paid", commit=False); action = "settled_paid"
        elif result.status in {"failed", "reversed"} and payout.status != "failed":
            await process_provider_result(session, payout.id, "failed", commit=False); action = "released_failed"
        elif result.status not in {"success", "successful", "failed", "reversed"}:
            action = "remains_processing"
        await _audit(session, entity_type="payout", entity_id=payout.id, provider=result.provider,
                     previous_state=previous, provider_state=result.status, resulting_state=payout.status,
                     action=action, success=True)
        await session.commit()
        return {"entity_type": "payout", "id": str(payout.id), "previous_state": previous,
                "provider_state": result.status, "resulting_state": payout.status, "action": action}
    except Exception as exc:
        await _failure_audit(session, "payout", payout.id, payout.provider, previous, "reconciliation_failed", exc)
        raise


async def reconcile_refund(session: AsyncSession, refund_id: UUID) -> dict[str, Any]:
    refund = await session.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
    if not refund:
        raise ReconciliationError("Refund not found")
    previous = refund.status
    try:
        provider = _provider()
        if refund.provider != provider.provider_name or not refund.provider_reference:
            raise ReconciliationError("Refund has no verifiable provider reference")
        result = await provider.verify_refund(refund.provider_reference)
        if result.currency != "NGN" or result.amount_ngn != refund.amount_ngn:
            raise ReconciliationError("Provider refund amount or currency does not match")
        mapped = "succeeded" if result.status in {"success", "processed", "succeeded"} else "failed" if result.status in {"failed", "reversed"} else "processing"
        action = "already_correct" if refund.status == mapped else f"transitioned_{mapped}"
        if refund.status != mapped:
            await process_refund_result(session, refund.id, mapped, commit=False)
        await _audit(session, entity_type="refund", entity_id=refund.id, provider=result.provider,
                     previous_state=previous, provider_state=result.status, resulting_state=refund.status,
                     action=action, success=True)
        await session.commit()
        return {"entity_type": "refund", "id": str(refund.id), "previous_state": previous,
                "provider_state": result.status, "resulting_state": refund.status, "action": action}
    except Exception as exc:
        await _failure_audit(session, "refund", refund.id, refund.provider, previous, "reconciliation_failed", exc)
        raise


def stale_cutoffs(now: datetime | None = None) -> dict[str, datetime]:
    now = now or datetime.now(timezone.utc)
    return {
        "payment": now - timedelta(minutes=settings.payment_reconciliation_after_minutes),
        "payout": now - timedelta(minutes=settings.payout_reconciliation_after_minutes),
        "refund": now - timedelta(minutes=settings.refund_reconciliation_after_minutes),
    }


async def stale_records(session: AsyncSession, now: datetime | None = None) -> dict[str, list[UUID]]:
    cutoffs = stale_cutoffs(now)
    payments = (await session.scalars(select(Payment.id).where(Payment.status.in_(["pending", "authorized"]), Payment.created_at < cutoffs["payment"])) ).all()
    payouts = (await session.scalars(select(Payout.id).where(Payout.status.in_(["pending", "processing"]), Payout.created_at < cutoffs["payout"])) ).all()
    refunds = (await session.scalars(select(Refund.id).where(Refund.status.in_(["pending", "processing"]), Refund.created_at < cutoffs["refund"])) ).all()
    return {"payments": list(payments), "payouts": list(payouts), "refunds": list(refunds)}


async def consistency_check(session: AsyncSession) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    tx_rows = (await session.execute(select(LedgerTransaction.id, func.sum(LedgerEntry.amount_ngn).filter(LedgerEntry.direction == "debit"), func.sum(LedgerEntry.amount_ngn).filter(LedgerEntry.direction == "credit")).join(LedgerEntry).group_by(LedgerTransaction.id))).all()
    for tx_id, debit, credit in tx_rows:
        if (debit or 0) != (credit or 0): anomalies.append({"type": "unbalanced_ledger", "id": str(tx_id)})
    captures = (await session.scalars(select(LedgerTransaction.source_id).where(LedgerTransaction.source_type == "payment", LedgerTransaction.transaction_type == "payment_capture"))).all()
    capture_ids = set(captures)
    for payment in (await session.scalars(select(Payment).where(Payment.status.in_(["paid", "partially_refunded", "refunded"])))):
        if payment.id not in capture_ids: anomalies.append({"type": "paid_payment_without_capture", "id": str(payment.id)})
    duplicate_caps = (await session.execute(select(LedgerTransaction.source_id, func.count()).where(LedgerTransaction.source_type == "payment", LedgerTransaction.transaction_type == "payment_capture").group_by(LedgerTransaction.source_id).having(func.count() > 1))).all()
    anomalies.extend({"type": "duplicate_capture", "id": str(x)} for x, _ in duplicate_caps)
    for reservation, payout in (await session.execute(select(PayoutReservation, Payout).join(Payout, Payout.id == PayoutReservation.payout_id))):
        if reservation.status == "consumed" and payout.status != "paid": anomalies.append({"type": "consumed_reservation_without_paid_payout", "id": str(reservation.id)})
        if reservation.status == "active" and payout.status == "failed": anomalies.append({"type": "active_reservation_on_failed_payout", "id": str(reservation.id)})
    reversal_ids = set((await session.scalars(select(LedgerTransaction.source_id).where(LedgerTransaction.source_type == "refund", LedgerTransaction.transaction_type == "refund_reversal"))).all())
    for refund in (await session.scalars(select(Refund).where(Refund.status == "succeeded"))):
        if refund.id not in reversal_ids: anomalies.append({"type": "succeeded_refund_without_reversal", "id": str(refund.id)})
    for payment in (await session.scalars(select(Payment).where(Payment.refunded_amount_ngn > Payment.amount_ngn))):
        anomalies.append({"type": "refunded_amount_exceeds_payment", "id": str(payment.id)})
    return anomalies
