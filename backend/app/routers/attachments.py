from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, Booking, ProfessionalProfile, ProjectAttachment
from ..storage import configured_storage, StorageError

router=APIRouter(); storage=configured_storage()
ALLOWED={"image/jpeg","image/png","image/webp","application/pdf","text/plain"}; MAX=10*1024*1024
async def owned(booking_id,user,db):
    b=await db.scalar(select(Booking).where(Booking.id==booking_id)); p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not b or (b.customer_id!=user.id and (not p or b.professional_id!=p.id)): raise HTTPException(404,"Booking not found")
    return b

@router.post("/{booking_id}",status_code=201)
async def upload(booking_id:UUID,file:UploadFile=File(...),user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    await owned(booking_id,user,db)
    if file.content_type not in ALLOWED: raise HTTPException(415,"File type not supported")
    data=await file.read()
    if len(data)>MAX: raise HTTPException(413,"File is larger than 10 MB")
    aid=uuid4(); suffix=Path(file.filename or "file").suffix[:10]; key=f"{aid}{suffix}"
    try: await storage.put(key, data, file.content_type or "application/octet-stream")
    except StorageError as exc: raise HTTPException(503, str(exc)) from exc
    item=ProjectAttachment(id=aid,booking_id=booking_id,uploaded_by=user.id,filename=file.filename or "file",mime_type=file.content_type or "application/octet-stream",size_bytes=len(data),storage_key=key)
    db.add(item); await db.commit(); await db.refresh(item)
    return {"id":str(item.id),"filename":item.filename,"mime_type":item.mime_type,"size_bytes":item.size_bytes}

@router.get("/{booking_id}")
async def list_attachments(booking_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    await owned(booking_id,user,db); rows=(await db.scalars(select(ProjectAttachment).where(ProjectAttachment.booking_id==booking_id).order_by(ProjectAttachment.created_at.desc()))).all()
    return [{"id":str(x.id),"filename":x.filename,"mime_type":x.mime_type,"size_bytes":x.size_bytes,"created_at":x.created_at} for x in rows]

@router.get("/file/{attachment_id}")
async def download(attachment_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    item=await db.scalar(select(ProjectAttachment).where(ProjectAttachment.id==attachment_id));
    if not item: raise HTTPException(404,"Attachment not found")
    await owned(item.booking_id,user,db); path=storage.download_path(item.storage_key)
    if path is None:
        try:
            url = await storage.download_url(item.storage_key, expires_seconds=300)
        except StorageError as exc: raise HTTPException(503, str(exc)) from exc
        if not url: raise HTTPException(404,"Attachment file missing")
        return {"id":str(item.id),"filename":item.filename,"mime_type":item.mime_type,"download_url":url,"expires_in":300}
    if not path.exists(): raise HTTPException(404,"Attachment file missing")
    return FileResponse(path,media_type=item.mime_type,filename=item.filename)
