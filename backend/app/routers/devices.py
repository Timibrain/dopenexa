from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, DeviceToken

router=APIRouter()
class DeviceIn(BaseModel):
    token:str=Field(min_length=20,max_length=512)
    platform:str=Field(default="ios",max_length=20)

@router.post("/register")
async def register_device(data:DeviceIn,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    item=await db.scalar(select(DeviceToken).where(DeviceToken.token==data.token))
    now=datetime.now(timezone.utc)
    if item:
        item.user_id=user.id; item.platform=data.platform; item.is_active=True; item.last_seen_at=now
    else:
        item=DeviceToken(user_id=user.id,token=data.token,platform=data.platform,last_seen_at=now); db.add(item)
    await db.commit(); return {"id":str(item.id),"registered":True}

@router.delete("/{device_id}")
async def unregister_device(device_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    item=await db.scalar(select(DeviceToken).where(DeviceToken.id==device_id,DeviceToken.user_id==user.id))
    if not item: raise HTTPException(404,"Device not found")
    item.is_active=False; await db.commit(); return {"id":str(item.id),"active":False}
