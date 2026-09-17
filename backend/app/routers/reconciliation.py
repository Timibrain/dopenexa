from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import require_role
from ..reconciliation import ReconciliationError, consistency_check, reconcile_payment, reconcile_payout, reconcile_refund, stale_records

router = APIRouter()

async def _run(fn, entity_id: UUID, db: AsyncSession):
    try:
        return await fn(db, entity_id)
    except ReconciliationError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.post("/payments/{payment_id}")
async def payment(payment_id: UUID, user=Depends(require_role("admin")), db: AsyncSession = Depends(get_db)):
    return await _run(reconcile_payment, payment_id, db)

@router.post("/payouts/{payout_id}")
async def payout(payout_id: UUID, user=Depends(require_role("admin")), db: AsyncSession = Depends(get_db)):
    return await _run(reconcile_payout, payout_id, db)

@router.post("/refunds/{refund_id}")
async def refund(refund_id: UUID, user=Depends(require_role("admin")), db: AsyncSession = Depends(get_db)):
    return await _run(reconcile_refund, refund_id, db)

@router.post("/batch")
async def batch(user=Depends(require_role("admin")), db: AsyncSession = Depends(get_db)):
    stale = await stale_records(db)
    results = []
    for entity_type, ids, fn in (("payments", stale["payments"], reconcile_payment), ("payouts", stale["payouts"], reconcile_payout), ("refunds", stale["refunds"], reconcile_refund)):
        for entity_id in ids:
            try: results.append(await fn(db, entity_id))
            except ReconciliationError as exc: results.append({"entity_type": entity_type[:-1], "id": str(entity_id), "error": str(exc)})
    return {"stale": {key: [str(item) for item in value] for key, value in stale.items()}, "results": results}

@router.get("/consistency")
async def consistency(user=Depends(require_role("admin")), db: AsyncSession = Depends(get_db)):
    anomalies = await consistency_check(db)
    return {"healthy": not anomalies, "anomalies": anomalies}
