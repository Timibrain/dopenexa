from datetime import datetime, time
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from .models import Role, ServiceType

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=2, max_length=120)
    role: Role = Role.customer
class LoginIn(BaseModel):
    email: EmailStr
    password: str
class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AppleAuthIn(BaseModel):
    identity_token: str = Field(min_length=20, max_length=20000)
    nonce: str = Field(min_length=16, max_length=256)
    role: Role | None = None
class ProfileIn(BaseModel):
    headline: str
    bio: str
    years_experience: int = Field(ge=0, le=80)
    service_area: str | None = None

class ServiceUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    service_type: ServiceType | None = None
    price_ngn: int | None = Field(default=None, ge=0)
    duration_minutes: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
class ServiceIn(BaseModel):
    name: str
    description: str = ""
    service_type: ServiceType
    price_ngn: int = Field(ge=0)
    duration_minutes: int | None = Field(default=None, ge=1)
class AvailabilityIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
class BookingIn(BaseModel):
    professional_id: UUID
    service_id: UUID
    starts_at: datetime
    ends_at: datetime | None = None
    customer_note: str | None = None
class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
class ReviewIn(BaseModel):
    booking_id: UUID
    rating: int = Field(ge=1, le=5)
    body: str | None = None
