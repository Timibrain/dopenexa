from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import require_role
from ..models import User, ProfessionalProfile, Service
from ..schemas import ServiceIn

router = APIRouter()

@router.get("/{service_id}")
async def get_service(service_id: UUID, db: AsyncSession = Depends(get_db)):
    service = await db.scalar(select(Service).where(Service.id == service_id))
    if not service:
        raise HTTPException(404, "Service not found")
    return {
        "id": str(service.id), "professional_id": str(service.professional_id),
        "name": service.name, "description": service.description,
        "service_type": service.service_type.value, "price_ngn": service.price_ngn,
        "duration_minutes": service.duration_minutes
    }

@router.post("/me", status_code=201)
async def create_service(
    data: ServiceIn,
    user: User = Depends(require_role("professional")),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if not profile:
        raise HTTPException(400, "Create your professional profile first")
    service = Service(professional_id=profile.id, name=data.name, description=data.description,
                      service_type=data.service_type, price_ngn=data.price_ngn,
                      duration_minutes=data.duration_minutes)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return {"id": str(service.id)}
