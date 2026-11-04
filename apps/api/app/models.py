from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, ForeignKey, Text, DateTime, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

class User(Identity, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default='admin')

class Session(Identity, Base):
    __tablename__ = 'sessions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class Recovery(Identity, Base):
    __tablename__ = 'password_recoveries'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class Business(Identity, Base):
    __tablename__ = 'businesses'
    __table_args__ = (UniqueConstraint('name', 'country', 'city', name='uq_business_location'),)
    name: Mapped[str] = mapped_column(String(200), index=True)
    country: Mapped[str] = mapped_column(String(80), index=True)
    city: Mapped[str] = mapped_column(String(100), default='')
    industry: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text, default='')
    website: Mapped[str] = mapped_column(String(2048), default='')
    website_status: Mapped[str] = mapped_column(String(40), default='Verification pending')
    status: Mapped[str] = mapped_column(String(40), default='Discovered', index=True)
    source: Mapped[str] = mapped_column(String(80), default='Manual')

class Contact(Identity, Base):
    __tablename__ = 'business_contacts'
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id', ondelete='CASCADE'), index=True)
    email: Mapped[str] = mapped_column(String(320), default='')
    phone: Mapped[str] = mapped_column(String(50), default='')

class Opportunity(Identity, Base):
    __tablename__ = 'opportunities'
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id', ondelete='CASCADE'), unique=True)
    stage: Mapped[str] = mapped_column(String(30), default='New Lead', index=True)
    value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default='USD')

class Note(Identity, Base):
    __tablename__ = 'notes'
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)

class FollowUp(Identity, Base):
    __tablename__ = 'follow_ups'
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id', ondelete='CASCADE'), index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    body: Mapped[str] = mapped_column(Text)
    done: Mapped[bool] = mapped_column(default=False)

class Audit(Identity, Base):
    __tablename__ = 'audit_logs'
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(36), default='')

class Preference(Base):
    __tablename__ = 'preferences'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
