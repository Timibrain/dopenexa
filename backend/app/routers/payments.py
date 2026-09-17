from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, Booking, Payment, BookingStatus, Notification, ProfessionalProfile, PaymentEvent, Refund
from ..config import settings
from ..payment_provider import PaystackProvider, ProviderError, configured_payment_provider
from ..refunds import RefundError, mark_refund_submitted, process_refund_result, request_refund
from ..webhook_processing import WebhookProcessingError, process_paystack_webhook, process_webhook

router = APIRouter(); provider = configured_payment_provider()

class RefundRequestIn(BaseModel):
    amount_ngn: int | None = Field(default=None, gt=0)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)

@router.post("/create", status_code=201)
async def create_payment(booking_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    booking = await db.scalar(select(Booking).where(Booking.id == booking_id, Booking.customer_id == user.id).with_for_update())
    if not booking: raise HTTPException(404, "Booking not found")
    existing = await db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    if existing:
        return {"payment_id":str(existing.id),"status":existing.status,"amount_ngn":existing.amount_ngn,"checkout_url":None,"provider":existing.provider,"message":"Existing payment session."}
    reference=f"dpx_{booking.id.hex}"
    checkout=await provider.create_checkout(booking.total_ngn,user.email,reference)
    commission=round(booking.total_ngn*0.10)
    payment=Payment(booking_id=booking.id,provider=checkout.provider,provider_reference=checkout.reference,status="pending",amount_ngn=booking.total_ngn,commission_ngn=commission,professional_payable_ngn=booking.total_ngn-commission,idempotency_key=str(uuid4()))
    db.add(payment); await db.commit(); await db.refresh(payment)
    return {"payment_id":str(payment.id),"status":payment.status,"amount_ngn":payment.amount_ngn,"checkout_url":checkout.checkout_url,"provider":checkout.provider,"provider_reference":checkout.reference,"access_code":checkout.access_code,"message":"Checkout session created."}

@router.get("/{payment_id}")
async def payment_status(payment_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    p = await db.scalar(select(Payment).where(Payment.id == payment_id))
    if not p: raise HTTPException(404,"Payment not found")
    b = await db.scalar(select(Booking).where(Booking.id == p.booking_id))
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if not b or (b.customer_id != user.id and (not profile or b.professional_id != profile.id)): raise HTTPException(403,"Not allowed")
    return {"payment_id":str(p.id),"status":p.status,"amount_ngn":p.amount_ngn,"provider":p.provider,"created_at":p.created_at}

@router.get("/verify/{payment_id}")
async def verify_payment(payment_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    payment = await db.scalar(select(Payment).where(Payment.id == payment_id))
    if not payment: raise HTTPException(404, "Payment not found")
    booking = await db.scalar(select(Booking).where(Booking.id == payment.booking_id))
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if not booking or (booking.customer_id != user.id and (not profile or booking.professional_id != profile.id)):
        raise HTTPException(403, "Not allowed")
    if payment.provider != "paystack" or not isinstance(provider, PaystackProvider):
        raise HTTPException(400, "Transaction verification is unavailable for the configured provider")
    try:
        result = await provider.verify_transaction(payment.provider_reference or "")
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"provider": result.provider, "reference": result.reference, "status": result.status, "amount_ngn": result.amount_ngn, "currency": result.currency}

@router.post("/refund/{booking_id}", status_code=201)
async def refund_booking(booking_id: UUID, data: RefundRequestIn | None = None, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    booking = await db.scalar(select(Booking).where(Booking.id == booking_id, Booking.customer_id == user.id))
    if not booking: raise HTTPException(404,"Booking not found")
    payment = await db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    if not payment: raise HTTPException(400,"No payment is available to refund")
    key = data.idempotency_key if data and data.idempotency_key else str(uuid4())
    try:
        result = await request_refund(db, payment_id=payment.id, amount_ngn=(data.amount_ngn if data else None), idempotency_key=key)
    except RefundError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not result.duplicate and isinstance((refund_provider := configured_payment_provider()), PaystackProvider):
        provider_amount = None if result.refund.amount_ngn == payment.amount_ngn else result.refund.amount_ngn
        try:
            provider_result = await refund_provider.refund(payment.provider_reference, provider_amount)
            result_refund = await mark_refund_submitted(db, result.refund.id, provider_result.provider_reference)
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc
    else:
        result_refund = result.refund
    if not result.duplicate:
        db.add(Notification(user_id=booking.customer_id, booking_id=booking.id, type="payment", title="Refund requested", body=f"A refund of ₦{result.refund.amount_ngn:,} was initiated."))
        await db.commit()
    return {"booking_id":str(booking.id),"payment_id":str(payment.id),"refund_id":str(result_refund.id),"amount_ngn":result_refund.amount_ngn,"status":result_refund.status,"duplicate":result.duplicate}

@router.post("/refund/{refund_id}/simulate-provider-result")
async def simulate_refund_result(refund_id: UUID, status: str = "succeeded", user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """Development-only provider completion hook."""
    if status not in {"processing", "succeeded", "failed"}: raise HTTPException(400, "Status must be processing, succeeded or failed")
    try:
        refund = await process_refund_result(db, refund_id, status)
    except RefundError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"refund_id": str(refund.id), "status": refund.status}

@router.post("/refund/{refund_id}/reconcile")
async def reconcile_refund(refund_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    refund = await db.scalar(select(Refund).where(Refund.id == refund_id))
    if not refund: raise HTTPException(404, "Refund not found")
    provider = configured_payment_provider()
    if not isinstance(provider, PaystackProvider) or not refund.provider_reference:
        raise HTTPException(400, "Paystack refund verification is unavailable")
    try: result = await provider.verify_refund(refund.provider_reference)
    except ProviderError as exc: raise HTTPException(502, str(exc)) from exc
    mapped = "succeeded" if result.status in {"success", "processed", "succeeded"} else "failed" if result.status in {"failed", "reversed"} else "processing"
    refund = await process_refund_result(db, refund.id, mapped)
    return {"refund_id": str(refund.id), "status": refund.status, "provider_status": result.status, "amount_ngn": result.amount_ngn, "currency": result.currency}

@router.post("/webhooks")
async def webhook(request: Request, x_signature: str | None = Header(default=None), x_paystack_signature: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    try:
        if x_paystack_signature is not None or isinstance(provider, PaystackProvider):
            result = await process_paystack_webhook(db, payload, x_paystack_signature)
        else:
            result = await process_webhook(db, payload, x_signature)
        return {"accepted": result.accepted, "processed": result.processed, "duplicate": result.duplicate}
    except WebhookProcessingError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
