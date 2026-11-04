import csv
import hashlib
import io
import secrets
import smtplib
from datetime import timedelta, datetime, timezone
from email.message import EmailMessage
from typing import Literal
from urllib.parse import urlencode
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from pwdlib import PasswordHash
from redis import Redis
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DB
from .config import settings
from .db import get_db
from .models import User, Session, Recovery, Business, Contact, Opportunity, Note, FollowUp, Audit, Preference, now

app = FastAPI(title='Zota API', version='0.1.0')
passwords = PasswordHash.recommended()
dummy_hash = passwords.hash(secrets.token_urlsafe(24))
redis = Redis.from_url(settings.redis_url)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def limit(key, maximum=10):
    if settings.testing:
        return
    try:
        count = redis.incr('limit:' + key)
        if count == 1:
            redis.expire('limit:' + key, 900)
        if count > maximum:
            raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, 'Authentication rate limiter unavailable')

def actor(request: Request, db: DB = Depends(get_db)):
    session = db.scalar(select(Session).where(Session.token_hash == digest(request.cookies.get('zota_session', '')), Session.expires_at > now()))
    if not session:
        raise HTTPException(401, 'Sign in to continue')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf):
        raise HTTPException(403, 'Invalid CSRF token')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, 'Session no longer valid')
    return user

def editor(user: User = Depends(actor)):
    if user.role not in ('admin', 'editor'):
        raise HTTPException(403, 'Editor role required')
    return user

def admin(user: User = Depends(actor)):
    if user.role != 'admin':
        raise HTTPException(403, 'Administrator role required')
    return user

def audit(db, user, action, entity=''):
    db.add(Audit(user_id=user.id, action=action, entity_id=entity))

@app.middleware('http')
async def security(request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('origin') != settings.app_origin:
            return Response('Origin not allowed', status_code=403)
        if int(request.headers.get('content-length', '0')) > 1_000_000:
            return Response('Request too large', status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

@app.get('/health')
def health():
    return {'status': 'ok', 'phase': 1}

@app.post('/auth/login')
def login(data: Login, request: Request, response: Response, db: DB = Depends(get_db)):
    limit('login:' + (request.client.host if request.client else 'unknown'), 30)
    limit('account:' + digest(data.email.lower()))
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    valid = passwords.verify(data.password, user.password_hash if user else dummy_hash)
    if not user or not valid:
        raise HTTPException(401, 'Invalid email or password')
    token, csrf = secrets.token_urlsafe(48), secrets.token_hex(32)
    db.add(Session(user_id=user.id, token_hash=digest(token), csrf=csrf, expires_at=now() + timedelta(hours=12)))
    audit(db, user, 'auth.login')
    db.commit()
    response.set_cookie('zota_session', token, httponly=True, secure=settings.secure_cookies, samesite='lax', max_age=43200, path='/')
    return {'email': user.email, 'role': user.role, 'csrf': csrf}

@app.get('/auth/me')
def me(request: Request, user: User = Depends(actor), db: DB = Depends(get_db)):
    session = db.scalar(select(Session).where(Session.token_hash == digest(request.cookies['zota_session'])))
    return {'email': user.email, 'role': user.role, 'csrf': session.csrf}

@app.post('/auth/logout')
def logout(request: Request, response: Response, user: User = Depends(actor), db: DB = Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash == digest(request.cookies['zota_session'])))
    audit(db, user, 'auth.logout')
    db.commit()
    response.delete_cookie('zota_session', path='/')
    return {'ok': True}

class Recover(BaseModel):
    email: EmailStr

@app.post('/auth/recover')
def recover(data: Recover, request: Request, db: DB = Depends(get_db)):
    limit('recover:' + (request.client.host if request.client else 'unknown'), 5)
    if not settings.smtp_host:
        raise HTTPException(503, 'Password recovery email is not configured. Contact your administrator.')
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user:
        token = secrets.token_urlsafe(48)
        db.execute(delete(Recovery).where(Recovery.user_id == user.id))
        db.add(Recovery(user_id=user.id, token_hash=digest(token), expires_at=now() + timedelta(minutes=30)))
        message = EmailMessage()
        message['Subject'], message['From'], message['To'] = 'Reset your Zota password', settings.mail_from, user.email
        message.set_content('Reset your password within 30 minutes: ' + settings.app_origin + '/?' + urlencode({'reset': token}))
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.starttls()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(503, 'Recovery email could not be delivered')
    return {'message': 'If the account exists, a reset link has been sent.'}

class Reset(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    password: str = Field(min_length=12, max_length=200)

@app.post('/auth/reset')
def reset(data: Reset, request: Request, db: DB = Depends(get_db)):
    limit('reset:' + (request.client.host if request.client else 'unknown'))
    recovery = db.scalar(select(Recovery).where(Recovery.token_hash == digest(data.token), Recovery.expires_at > now()).with_for_update())
    if not recovery:
        raise HTTPException(400, 'Reset link is invalid or expired')
    user = db.get(User, recovery.user_id)
    user.password_hash = passwords.hash(data.password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    db.execute(delete(Recovery).where(Recovery.user_id == user.id))
    audit(db, user, 'auth.password_reset')
    db.commit()
    return {'ok': True}

Status = Literal['Discovered', 'Researching', 'Qualified', 'Draft ready', 'Awaiting approval', 'Approved', 'Sent', 'Replied', 'Interested', 'Not interested', 'Follow-up required', 'Converted', 'Do not contact']
Stage = Literal['New Lead', 'Contacted', 'Replied', 'Interested', 'Quotation', 'Negotiation', 'Won', 'Lost']
WebsiteStatus = Literal['Verified official website', 'Website likely exists', 'No official website found', 'Verification pending', 'Insufficient information']

class LeadInput(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    country: str = Field(min_length=2, max_length=80)
    city: str = Field(default='', max_length=100)
    industry: str = Field(min_length=2, max_length=100)
    description: str = Field(default='', max_length=5000)
    website: str = Field(default='', max_length=2048)
    email: EmailStr | Literal[''] = ''
    phone: str = Field(default='', max_length=50)
    @field_validator('name', 'country', 'industry', 'city', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value
    @field_validator('country')
    @classmethod
    def exclude_uganda(cls, value):
        if value.casefold() in ('uganda', 'ug', 'uga'):
            raise ValueError('Uganda is excluded from target markets')
        return value
    @field_validator('website')
    @classmethod
    def website_url(cls, value):
        if value and not value.startswith(('https://', 'http://')):
            raise ValueError('Website must use http or https')
        return value

class LeadUpdate(LeadInput):
    status: Status = 'Discovered'
    website_status: WebsiteStatus = 'Verification pending'
    stage: Stage = 'New Lead'
    value: float = Field(default=0, ge=0, le=999999999)

def serialize(db, lead):
    contact = db.scalar(select(Contact).where(Contact.business_id == lead.id))
    deal = db.scalar(select(Opportunity).where(Opportunity.business_id == lead.id))
    return {**{key: getattr(lead, key) for key in ('id', 'name', 'country', 'city', 'industry', 'description', 'website', 'website_status', 'status', 'source', 'created_at')}, 'email': contact.email if contact else '', 'phone': contact.phone if contact else '', 'stage': deal.stage if deal else 'New Lead', 'value': float(deal.value) if deal else 0}

def find(db, id):
    lead = db.get(Business, id)
    if not lead:
        raise HTTPException(404, 'Business not found')
    return lead

@app.get('/leads')
def leads(user: User = Depends(actor), db: DB = Depends(get_db)):
    return [serialize(db, lead) for lead in db.scalars(select(Business).order_by(Business.created_at.desc()))]

def insert(db, data, source='Manual'):
    lead = Business(**data.model_dump(exclude={'email', 'phone'}), source=source)
    db.add(lead)
    db.flush()
    db.add(Contact(business_id=lead.id, email=data.email, phone=data.phone))
    db.add(Opportunity(business_id=lead.id))
    db.flush()
    return lead

@app.post('/leads', status_code=201)
def create_lead(data: LeadUpdate, user: User = Depends(editor), db: DB = Depends(get_db)):
    try:
        lead = insert(db, LeadInput.model_validate(data.model_dump()))
        lead.status, lead.website_status = data.status, data.website_status
        deal = db.scalar(select(Opportunity).where(Opportunity.business_id == lead.id))
        deal.stage, deal.value = data.stage, data.value
        audit(db, user, 'lead.created', lead.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'A business with this name and location already exists')
    return serialize(db, lead)

@app.put('/leads/{id}')
def update_lead(id: str, data: LeadUpdate, user: User = Depends(editor), db: DB = Depends(get_db)):
    lead = find(db, id)
    for key, value in data.model_dump(exclude={'email', 'phone', 'stage', 'value'}).items():
        setattr(lead, key, value)
    contact = db.scalar(select(Contact).where(Contact.business_id == id))
    contact.email, contact.phone = data.email, data.phone
    deal = db.scalar(select(Opportunity).where(Opportunity.business_id == id))
    deal.stage, deal.value = data.stage, data.value
    if data.status in ('Do not contact', 'Not interested'):
        for follow in db.scalars(select(FollowUp).where(FollowUp.business_id == id)):
            follow.done = True
    audit(db, user, 'lead.updated', id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Duplicate business and location')
    return serialize(db, lead)

@app.delete('/leads/{id}')
def delete_lead(id: str, user: User = Depends(admin), db: DB = Depends(get_db)):
    lead = find(db, id)
    for model in (Contact, Opportunity, Note, FollowUp):
        db.execute(delete(model).where(model.business_id == id))
    db.delete(lead)
    audit(db, user, 'lead.deleted', id)
    db.commit()
    return {'ok': True}

class CSVInput(BaseModel):
    content: str = Field(max_length=500000)

@app.post('/leads/import')
def import_csv(data: CSVInput, user: User = Depends(editor), db: DB = Depends(get_db)):
    rows = list(csv.DictReader(io.StringIO(data.content)))
    if not rows or len(rows) > 1000:
        raise HTTPException(422, 'Import must contain 1–1000 rows')
    try:
        validated = [LeadInput.model_validate(row) for row in rows]
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    try:
        for row in validated:
            insert(db, row, 'CSV import')
        audit(db, user, 'leads.imported')
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Import contains duplicate businesses. No rows were imported.')
    return {'imported': len(rows)}

@app.get('/export')
def export(user: User = Depends(actor), db: DB = Depends(get_db)):
    output = io.StringIO()
    fields = ['name', 'country', 'city', 'industry', 'description', 'website', 'email', 'phone']
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for lead in db.scalars(select(Business)):
        row = serialize(db, lead)
        writer.writerow({k: "'" + str(row[k]) if str(row[k]).lstrip().startswith(('=', '+', '-', '@')) else row[k] for k in fields})
    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=zota-leads.csv'})

class NoteInput(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

@app.get('/leads/{id}/notes')
def notes(id: str, user: User = Depends(actor), db: DB = Depends(get_db)):
    find(db, id)
    return list(db.scalars(select(Note).where(Note.business_id == id).order_by(Note.created_at.desc())))

@app.post('/leads/{id}/notes', status_code=201)
def add_note(id: str, data: NoteInput, user: User = Depends(editor), db: DB = Depends(get_db)):
    find(db, id)
    note = Note(business_id=id, user_id=user.id, body=data.body)
    db.add(note)
    audit(db, user, 'note.created', id)
    db.commit()
    return note

class FollowInput(NoteInput):
    business_id: str
    due_at: datetime
    @field_validator('due_at')
    @classmethod
    def utc_due_at(cls, value):
        if value.tzinfo is None:
            raise ValueError('Reminder timestamp must include a timezone')
        return value.astimezone(timezone.utc).replace(tzinfo=None)

@app.get('/follow-ups')
def follows(user: User = Depends(actor), db: DB = Depends(get_db)):
    return list(db.scalars(select(FollowUp).order_by(FollowUp.due_at)))

@app.post('/follow-ups', status_code=201)
def add_follow(data: FollowInput, user: User = Depends(editor), db: DB = Depends(get_db)):
    lead = find(db, data.business_id)
    if lead.status in ('Not interested', 'Do not contact'):
        raise HTTPException(409, 'Follow-ups are blocked for this business')
    follow = FollowUp(**data.model_dump())
    db.add(follow)
    audit(db, user, 'follow_up.created', lead.id)
    db.commit()
    return follow

@app.post('/follow-ups/{id}/complete')
def complete_follow(id: str, user: User = Depends(editor), db: DB = Depends(get_db)):
    follow = db.get(FollowUp, id)
    if not follow:
        raise HTTPException(404, 'Follow-up not found')
    follow.done = True
    audit(db, user, 'follow_up.completed', id)
    db.commit()
    return {'ok': True}

@app.get('/audit')
def logs(user: User = Depends(admin), db: DB = Depends(get_db)):
    return list(db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)))

@app.get('/settings')
def preferences(user: User = Depends(actor), db: DB = Depends(get_db)):
    return {p.key: p.value for p in db.scalars(select(Preference))}

class Preferences(BaseModel):
    business_name: str = Field(max_length=200)
    sender_name: str = Field(max_length=200)
    target_countries: str = Field(max_length=1000)

@app.put('/settings')
def save_preferences(data: Preferences, user: User = Depends(admin), db: DB = Depends(get_db)):
    if any(c.strip().lower() in ('uganda', 'ug', 'uga') for c in data.target_countries.split(',')):
        raise HTTPException(422, 'Uganda is excluded from target markets')
    for key, value in data.model_dump().items():
        db.merge(Preference(key=key, value=value))
    audit(db, user, 'settings.updated')
    db.commit()
    return data
