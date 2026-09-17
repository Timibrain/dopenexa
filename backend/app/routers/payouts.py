from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import require_role
from ..models import User, ProfessionalProfile, PayoutAccount, Payout
from ..config import settings
from ..payment_provider import PaystackProvider, ProviderError, configured_payment_provider
from ..payouts import PayoutError, available_balance, mark_transfer_initialized, process_provider_result, request_payout as create_payout

router=APIRouter()
class PayoutAccountIn(BaseModel):
    provider:str=Field(default="pending",max_length=50)
    account_name:str=Field(min_length=2,max_length=160)
    account_reference:str=Field(min_length=2,max_length=255)
    bank_code:str|None=Field(default=None,max_length=20)

class PayoutRequestIn(BaseModel):
    amount_ngn: int | None = Field(default=None, gt=0)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)

@router.put("/account")
async def save_account(data:PayoutAccountIn,user:User=Depends(require_role("professional")),db:AsyncSession=Depends(get_db)):
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not p: raise HTTPException(400,"Create a professional profile first")
    old=await db.scalars(select(PayoutAccount).where(PayoutAccount.professional_id==p.id)); [setattr(x,"is_default",False) for x in old]
    item=PayoutAccount(professional_id=p.id,**data.model_dump(),is_default=True); db.add(item); await db.commit(); await db.refresh(item)
    return {"id":str(item.id),"provider":item.provider,"account_name":item.account_name,"account_reference":item.account_reference}

@router.get("/balance")
async def balance(user:User=Depends(require_role("professional")),db:AsyncSession=Depends(get_db)):
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not p: raise HTTPException(400,"Create a professional profile first")
    available=await available_balance(db,p.id)
    return {"earned_ngn":int(available),"paid_out_ngn":0,"available_ngn":int(available),"minimum_payout_ngn":settings.minimum_payout_ngn}

@router.get("")
async def list_payouts(user:User=Depends(require_role("professional")),db:AsyncSession=Depends(get_db)):
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    rows=(await db.scalars(select(Payout).where(Payout.professional_id==p.id).order_by(Payout.created_at.desc()))).all() if p else []
    return [{"id":str(x.id),"amount_ngn":x.amount_ngn,"status":x.status,"provider":x.provider,"provider_reference":x.provider_reference,"created_at":x.created_at,"paid_at":x.paid_at} for x in rows]

@router.post("",status_code=201)
async def request_payout(data:PayoutRequestIn|None=None,user:User=Depends(require_role("professional")),db:AsyncSession=Depends(get_db)):
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not p: raise HTTPException(400,"Create a professional profile first")
    key=(data.idempotency_key if data and data.idempotency_key else str(uuid4()))
    try:
        result=await create_payout(db,professional_id=p.id,amount_ngn=(data.amount_ngn if data else None),idempotency_key=key,minimum_ngn=settings.minimum_payout_ngn)
    except PayoutError as exc: raise HTTPException(400,str(exc))
    item=result.payout
    if isinstance(configured_payment_provider(), PaystackProvider) and (not result.duplicate or not item.provider_reference):
        provider = configured_payment_provider()
        account=await db.scalar(select(PayoutAccount).where(PayoutAccount.professional_id==p.id,PayoutAccount.is_default.is_(True)))
        try:
            if not account.provider_recipient_code:
                recipient=await provider.create_transfer_recipient(account.account_name,account.account_reference,account.bank_code)
                account.provider_recipient_code=recipient.recipient_code
                await db.commit()
            transfer=await provider.initiate_transfer(item.amount_ngn,account.provider_recipient_code,item.dopenexa_reference)
            item=await mark_transfer_initialized(db,item.id,transfer.transfer_code or transfer.reference)
        except ProviderError as exc:
            raise HTTPException(502,str(exc)) from exc
    return {"id":str(item.id),"reference":item.dopenexa_reference,"amount_ngn":item.amount_ngn,"status":item.status,"provider":item.provider,
            "provider_reference":item.provider_reference,"created_at":item.created_at,"paid_at":item.paid_at,
            "message":"Payout queued for the configured provider."}

@router.post("/{payout_id}/simulate-provider-result")
async def simulate_provider_result(payout_id:UUID, status:str="paid", user:User=Depends(require_role("admin")), db:AsyncSession=Depends(get_db)):
    """Development-only settlement hook. Production providers should call a signed webhook instead."""
    if status not in {"paid","failed"}: raise HTTPException(400,"Status must be paid or failed")
    try: item=await process_provider_result(db,payout_id,status)
    except PayoutError as exc: raise HTTPException(400,str(exc))
    return {"id":str(item.id),"status":item.status}

@router.post("/{payout_id}/reconcile")
async def reconcile_payout(payout_id:UUID, user:User=Depends(require_role("admin")), db:AsyncSession=Depends(get_db)):
    provider=configured_payment_provider()
    item=await db.scalar(select(Payout).where(Payout.id==payout_id))
    if not item: raise HTTPException(404,"Payout not found")
    if not isinstance(provider, PaystackProvider) or not item.provider_reference:
        raise HTTPException(400,"Paystack transfer verification is unavailable")
    try: result=await provider.verify_transfer(item.provider_reference)
    except ProviderError as exc: raise HTTPException(502,str(exc)) from exc
    mapped = "paid" if result.status in {"success","successful"} else "failed" if result.status in {"failed","reversed"} else None
    if mapped: item=await process_provider_result(db,item.id,mapped)
    return {"id":str(item.id),"status":item.status,"provider_status":result.status,"amount_ngn":result.amount_ngn,"currency":result.currency}
