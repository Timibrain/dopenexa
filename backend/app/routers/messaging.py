from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, Conversation, ConversationMember, Message
from ..schemas import MessageIn

router = APIRouter()

async def member(conversation_id: UUID, user_id: UUID, db: AsyncSession):
    return await db.scalar(select(ConversationMember).where(
        ConversationMember.conversation_id == conversation_id,
        ConversationMember.user_id == user_id
    ))

@router.get("")
async def list_conversations(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Conversation).join(
        ConversationMember, ConversationMember.conversation_id == Conversation.id
    ).where(ConversationMember.user_id == user.id))).all()
    return [{"id": str(c.id), "booking_id": str(c.booking_id) if c.booking_id else None} for c in rows]

@router.get("/{conversation_id}/messages")
async def list_messages(conversation_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not await member(conversation_id, user.id, db):
        raise HTTPException(403, "Not a conversation member")
    rows = (await db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at))).all()
    return [{"id": str(m.id), "sender_id": str(m.sender_id), "body": m.body, "created_at": m.created_at} for m in rows]

@router.post("/{conversation_id}/messages", status_code=201)
async def send_message(conversation_id: UUID, data: MessageIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    if not await member(conversation_id, user.id, db):
        raise HTTPException(403, "Not a conversation member")
    m = Message(conversation_id=conversation_id, sender_id=user.id, body=data.body)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return {"id": str(m.id), "sender_id": str(m.sender_id), "body": m.body, "created_at": m.created_at}
