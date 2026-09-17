import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .payment_provider import PaystackProvider, ProviderError
from .models import Booking, BookingStatus, Payment, PaymentEvent, PaymentStatusHistory, Payout, Refund
from .payment_transitions import PaymentTransitionError, transition_payment
from .payouts import PayoutError, process_provider_result
from .refunds import RefundError, process_refund_result


class WebhookProcessingError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PaymentWebhook:
    provider: str
    event_id: str
    event_type: str
    provider_reference: str
    amount_ngn: int
    currency: str
    status: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class WebhookResult:
    accepted: bool
    processed: bool
    duplicate: bool = False


def _verify_signature(payload: bytes, signature: str | None) -> None:
    expected = hmac.new(settings.payment_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise WebhookProcessingError("Invalid webhook signature", 401)


def _parse(payload: bytes) -> PaymentWebhook:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WebhookProcessingError("Invalid JSON") from exc
    if not isinstance(data, dict):
        raise WebhookProcessingError("Webhook payload must be an object")

    provider = data.get("provider")
    event_id = data.get("event_id") or data.get("id")
    event_type = data.get("event_type") or data.get("type")
    provider_reference = data.get("reference") or data.get("provider_reference")
    currency = str(data.get("currency") or "").upper()
    status = str(data.get("status") or "").lower()
    amount = data.get("amount")
    if not all(isinstance(value, str) and value.strip() for value in (provider, event_id, event_type, provider_reference)):
        raise WebhookProcessingError("provider, event ID, event type, and provider reference are required")
    if isinstance(amount, bool) or not isinstance(amount, (int, str)):
        raise WebhookProcessingError("amount must be an integer NGN value")
    try:
        amount_ngn = int(amount)
    except (TypeError, ValueError) as exc:
        raise WebhookProcessingError("amount must be an integer NGN value") from exc
    if amount_ngn <= 0:
        raise WebhookProcessingError("amount must be positive")
    if currency != "NGN":
        raise WebhookProcessingError("currency must be NGN")
    return PaymentWebhook(
        provider=provider.strip(),
        event_id=event_id.strip(),
        event_type=event_type.strip(),
        provider_reference=provider_reference.strip(),
        amount_ngn=amount_ngn,
        currency=currency,
        status=status,
        payload=data,
    )


async def _claim_event(session: AsyncSession, event: PaymentWebhook) -> tuple[PaymentEvent, bool]:
    statement = insert(PaymentEvent).values(
        provider=event.provider,
        event_id=event.event_id,
        event_type=event.event_type,
        payload=event.payload,
        processing_status="received",
        processed_at=None,
        failure_reason=None,
    ).on_conflict_do_nothing(index_elements=["provider", "event_id"])
    inserted = (await session.execute(statement)).rowcount == 1
    record = await session.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider == event.provider,
            PaymentEvent.event_id == event.event_id,
        ).with_for_update()
    )
    if not record:
        raise WebhookProcessingError("Could not claim webhook event", 500)
    return record, inserted


async def _record_failure(session: AsyncSession, event: PaymentWebhook, reason: str) -> None:
    """Persist a validated event failure without retaining partial financial work."""
    try:
        await session.rollback()
        record, _ = await _claim_event(session, event)
        if record.processing_status != "processed":
            record.processing_status = "failed"
            record.failure_reason = reason[:2000]
            record.processed_at = datetime.now(timezone.utc)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def process_webhook(session: AsyncSession, payload: bytes, signature: str | None, *, verify_signature: bool = True) -> WebhookResult:
    """Verify, claim, validate, transition, and commit one provider event."""
    if verify_signature:
        _verify_signature(payload, signature)
    event = _parse(payload)
    try:
        event_record, inserted = await _claim_event(session, event)
        if not inserted:
            if event_record.processing_status in {"processed", "failed"}:
                await session.commit()
                return WebhookResult(accepted=True, processed=False, duplicate=True)

        payment = await session.scalar(
            select(Payment).where(Payment.provider_reference == event.provider_reference).with_for_update()
        )
        if not payment:
            raise WebhookProcessingError("Payment does not exist")
        if payment.provider != event.provider:
            raise WebhookProcessingError("Webhook provider does not match payment")
        if payment.provider_reference != event.provider_reference:
            raise WebhookProcessingError("Webhook provider reference does not match payment")
        if payment.amount_ngn != event.amount_ngn:
            raise WebhookProcessingError("Webhook amount does not match payment")
        if payment.currency != event.currency:
            raise WebhookProcessingError("Webhook currency does not match payment")

        target_status = "paid" if event.status in {"success", "paid", "successful"} else "failed" if event.status in {"failed", "cancelled", "abandoned"} else None
        if event.status in {"pending", "ongoing", "processing", "queued"}:
            event_record.processing_status = "processed"
            event_record.processed_at = datetime.now(timezone.utc)
            await session.commit()
            return WebhookResult(accepted=True, processed=True, duplicate=False)
        if not target_status:
            raise WebhookProcessingError("Unsupported payment webhook status")
        await transition_payment(
            session,
            payment.id,
            target_status,
            source=f"webhook:{event.provider}",
            transition_key=f"webhook:{event.provider}:{event.event_id}",
            commit=False,
        )
        booking = await session.scalar(select(Booking).where(Booking.id == payment.booking_id).with_for_update())
        if target_status == "paid" and booking and booking.status == BookingStatus.pending:
            booking.status = BookingStatus.confirmed
        event_record.processing_status = "processed"
        event_record.processed_at = datetime.now(timezone.utc)
        event_record.failure_reason = None
        await session.commit()
        return WebhookResult(accepted=True, processed=True, duplicate=False)
    except (WebhookProcessingError, PaymentTransitionError) as exc:
        await _record_failure(session, event, str(exc))
        raise WebhookProcessingError(str(exc), getattr(exc, "status_code", 400)) from exc
    except Exception:
        await session.rollback()
        raise


async def process_paystack_webhook(session: AsyncSession, payload: bytes, signature: str | None) -> WebhookResult:
    """Verify Paystack's raw SHA-512 signature, normalize kobo data, then use Phase 2."""
    if not settings.paystack_secret_key:
        raise WebhookProcessingError("Paystack is not configured", 503)
    try:
        PaystackProvider.verify_webhook_signature(payload, signature, settings.paystack_secret_key)
        data = json.loads(payload)
        event_data = data.get("data") or {}
        event_type = data.get("event") or "paystack.event"
        if str(event_type).startswith("transfer."):
            return await _process_paystack_transfer_webhook(session, payload, data, event_type)
        if str(event_type).startswith("refund."):
            return await _process_paystack_refund_webhook(session, payload, data, event_type)
        amount_kobo = int(event_data.get("amount"))
        if amount_kobo <= 0 or amount_kobo % 100:
            raise WebhookProcessingError("Paystack amount is not a whole NGN value")
        reference = event_data.get("reference")
        event_id = str(event_data.get("id") or data.get("id") or f"{event_type}:{reference}:{event_data.get('status')}")
        normalized = {
            "provider": "paystack", "event_id": event_id, "event_type": event_type,
            "reference": reference, "amount": amount_kobo // 100,
            "currency": str(event_data.get("currency") or "").upper(),
            "status": str(event_data.get("status") or "").lower(),
            "paystack_payload": data,
        }
        if not reference:
            raise WebhookProcessingError("Paystack event has no transaction reference")
        return await process_webhook(session, json.dumps(normalized).encode(), None, verify_signature=False)
    except ProviderError as exc:
        raise WebhookProcessingError(str(exc), 401) from exc
    except WebhookProcessingError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WebhookProcessingError("Malformed Paystack webhook payload") from exc


async def _process_paystack_refund_webhook(session: AsyncSession, raw_payload: bytes, data: dict[str, Any], event_type: str) -> WebhookResult:
    event_data = data.get("data") or {}
    try:
        amount_kobo = int(event_data.get("amount"))
        if amount_kobo <= 0 or amount_kobo % 100:
            raise WebhookProcessingError("Paystack refund amount is invalid")
        provider_reference = str(event_data.get("id") or event_data.get("refund_id") or "")
        transaction = event_data.get("transaction") or event_data.get("transaction_reference") or event_data.get("reference")
        if isinstance(transaction, dict): transaction = transaction.get("reference")
        transaction = str(transaction or "")
        event_id = str(event_data.get("event_id") or data.get("id") or f"{event_type}:{provider_reference}:{transaction}")
        event = PaymentWebhook(provider="paystack", event_id=event_id, event_type=event_type,
                               provider_reference=provider_reference or transaction, amount_ngn=amount_kobo // 100,
                               currency=str(event_data.get("currency") or "").upper(),
                               status=str(event_data.get("status") or "").lower(), payload=data)
        record, inserted = await _claim_event(session, event)
        if not inserted and record.processing_status in {"processed", "failed"}:
            await session.commit()
            return WebhookResult(accepted=True, processed=False, duplicate=True)
        if event.currency != "NGN": raise WebhookProcessingError("Paystack refund currency must be NGN")
        refund = await session.scalar(select(Refund).where(
            (Refund.provider_reference == provider_reference) | (Refund.payment_id.in_(select(Payment.id).where(Payment.provider_reference == transaction))),
            Refund.status.in_(["pending", "processing"]),
        ).with_for_update())
        if not refund: raise WebhookProcessingError("Refund does not exist")
        if refund.amount_ngn != event.amount_ngn: raise WebhookProcessingError("Refund amount does not match request")
        status = event.status
        if status in {"pending", "processing", "queued"}:
            await process_refund_result(session, refund.id, "processing", commit=False)
        elif status in {"success", "succeeded", "processed"}:
            await process_refund_result(session, refund.id, "succeeded", commit=False)
        elif status in {"failed", "reversed"}:
            await process_refund_result(session, refund.id, "failed", commit=False)
        else:
            raise WebhookProcessingError("Unsupported Paystack refund status")
        record.processing_status = "processed"; record.processed_at = datetime.now(timezone.utc); record.failure_reason = None
        await session.commit()
        return WebhookResult(accepted=True, processed=True)
    except (WebhookProcessingError, RefundError) as exc:
        event = locals().get("event")
        if event is not None: await _record_failure(session, event, str(exc))
        raise WebhookProcessingError(str(exc)) from exc
    except Exception:
        await session.rollback()
        raise


async def _process_paystack_transfer_webhook(session: AsyncSession, raw_payload: bytes, data: dict[str, Any], event_type: str) -> WebhookResult:
    event_data = data.get("data") or {}
    try:
        amount_kobo = int(event_data.get("amount"))
        if amount_kobo <= 0 or amount_kobo % 100:
            raise WebhookProcessingError("Paystack transfer amount is invalid")
        transfer_code = str(event_data.get("transfer_code") or "")
        reference = str(event_data.get("reference") or transfer_code)
        event_id = str(event_data.get("id") or data.get("id") or f"{event_type}:{reference}")
        event = PaymentWebhook(provider="paystack", event_id=event_id, event_type=event_type,
                               provider_reference=reference, amount_ngn=amount_kobo // 100,
                               currency=str(event_data.get("currency") or "").upper(),
                               status=str(event_data.get("status") or "").lower(), payload=data)
        record, inserted = await _claim_event(session, event)
        if not inserted and record.processing_status in {"processed", "failed"}:
            await session.commit()
            return WebhookResult(accepted=True, processed=False, duplicate=True)
        if event.currency != "NGN": raise WebhookProcessingError("Paystack transfer currency must be NGN")
        payout = await session.scalar(select(Payout).where(
            (Payout.dopenexa_reference == reference) | (Payout.provider_reference == (transfer_code or reference))
        ).with_for_update())
        if not payout: raise WebhookProcessingError("Payout does not exist")
        if payout.provider != "paystack": raise WebhookProcessingError("Transfer provider does not match payout")
        if payout.amount_ngn != event.amount_ngn: raise WebhookProcessingError("Transfer amount does not match payout")
        if event.status in {"pending", "ongoing", "processing", "queued"}:
            record.processing_status = "processed"; record.processed_at = datetime.now(timezone.utc); await session.commit()
            return WebhookResult(accepted=True, processed=True)
        target = "paid" if event.status in {"success", "successful"} else "failed" if event.status in {"failed", "reversed"} else None
        if not target: raise WebhookProcessingError("Unsupported Paystack transfer status")
        await process_provider_result(session, payout.id, target, commit=False)
        record.processing_status = "processed"; record.processed_at = datetime.now(timezone.utc); record.failure_reason = None
        await session.commit()
        return WebhookResult(accepted=True, processed=True)
    except (WebhookProcessingError, PayoutError) as exc:
        event = locals().get("event")
        if event is not None:
            await _record_failure(session, event, str(exc))
        raise WebhookProcessingError(str(exc)) from exc
    except Exception:
        await session.rollback()
        raise
