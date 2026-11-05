"""Bounded discovery and one-time outreach. Provider credentials stay server-side."""
import json
import re
import secrets
import smtplib
from datetime import timedelta, datetime
from email.message import EmailMessage
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Prospect, Outreach, Suppression, Preference, Business, Contact, Opportunity, now

SOCIAL = {'facebook.com','instagram.com','tiktok.com','yelp.com','yellowpages.com','bbb.org','mapquest.com','google.com'}

def safe_url(value):
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in ('https','http') and parsed.hostname and not parsed.username else ''
    except ValueError:
        return ''

def directory_url(value):
    host = (urlsplit(value).hostname or '').lower()
    return any(host == domain or host.endswith('.'+domain) for domain in SOCIAL)

def prefs(db):
    return {p.key:p.value for p in db.scalars(select(Preference))}

def request_json(method, url, **kwargs):
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            response = client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'Provider request failed. Check credentials, quota, and provider account status.')

def discover(city, industry):
    if not settings.google_places_api_key or not settings.brave_search_api_key:
        raise HTTPException(503, 'Connect Google Places and Brave Search in Integrations before discovery.')
    data = request_json('POST','https://places.googleapis.com/v1/places:searchText',
        headers={'X-Goog-Api-Key':settings.google_places_api_key,'X-Goog-FieldMask':'places.id,places.displayName,places.addressComponents,places.formattedAddress,places.websiteUri,places.googleMapsUri,places.businessStatus'},
        json={'textQuery':f'{industry} in {city}, United States','regionCode':'US','pageSize':5})
    candidates, rejected = [], []
    for place in data.get('places',[]):
        countries = [c.get('shortText') for c in place.get('addressComponents',[]) if 'country' in c.get('types',[])]
        if countries != ['US'] or place.get('websiteUri') or place.get('businessStatus') != 'OPERATIONAL':
            rejected.append(place.get('id',''))
            continue
        name = place.get('displayName',{}).get('text','')
        if not name or not place.get('id'):
            rejected.append(place.get('id',''))
            continue
        address = place.get('formattedAddress','')
        query = f'"{name}" {address} official website'
        result = request_json('GET','https://api.search.brave.com/res/v1/web/search',
            headers={'X-Subscription-Token':settings.brave_search_api_key},
            params={'q':query[:400],'country':'US','count':10})
        links = [{'title':r.get('title',''),'url':safe_url(r.get('url',''))} for r in result.get('web',{}).get('results',[])]
        links = [r for r in links if r['url']]
        # Fail closed: zero results or any possible independent website is ambiguous.
        if not links or any(not directory_url(r['url']) for r in links):
            rejected.append(place.get('id',''))
            continue
        candidates.append({'place_id':place['id'],'name':name[:200],'city':city,'industry':industry,
            'evidence':json.dumps({'country':'US','address':address,'listing':safe_url(place.get('googleMapsUri','')),
                'query':query,'links':links,'checked_at':now().isoformat(),'finding':'No official website found; review required. Absence cannot be proven by search.'})})
    return candidates, rejected

class SearchInput(BaseModel):
    city: str = Field(min_length=3,max_length=100)
    industry: str = Field(min_length=3,max_length=80)

class QualifyInput(BaseModel):
    name: str = Field(min_length=2,max_length=200)
    email: EmailStr | None = None
    phone: str = Field(default='',max_length=30)
    contact_source: str = Field(min_length=10,max_length=2000)
    verification_note: str = Field(min_length=20,max_length=2000)
    confirmed_no_website: bool
    whatsapp_consent: str = Field(default='',max_length=2000)

class CampaignInput(BaseModel):
    postal_address: str = Field(default='',max_length=500)
    city: str = Field(default='Austin, Texas',min_length=3,max_length=100)
    industry: str = Field(default='barbers',min_length=3,max_length=80)
    automatic_discovery: bool = False
    automatic_email: bool = False

class DraftInput(BaseModel):
    business_id: str
    channel: str = Field(pattern='^(email|whatsapp)$')

class ReplyInput(BaseModel):
    body: str = Field(min_length=1,max_length=5000)
    stop: bool = False

def readiness(db):
    p = prefs(db)
    return {'google':bool(settings.google_places_api_key),'search':bool(settings.brave_search_api_key),
        'email':bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.mail_from),
        'whatsapp':False,
        'postal_address':bool(p.get('postal_address','').strip()),'scheduler':bool(settings.cron_secret),
        'sender_name':p.get('sender_name','Opaki'),'sender_email':p.get('sender_email',''),
        'sender_whatsapp':p.get('sender_whatsapp',''),'country':'United States','service':'Website design'}

def eligible(db, lead, recipient):
    if not lead or lead.country != 'United States' or lead.website or lead.website_status != 'No official website found':
        raise HTTPException(409,'Only verified US businesses without a website can receive outreach.')
    if lead.status in ('Do not contact','Not interested','Replied','Interested','Converted') or db.get(Suppression,recipient.lower()):
        raise HTTPException(409,'This recipient is suppressed or has already replied.')
    prospect = db.scalar(select(Prospect).where(Prospect.business_id==lead.id,Prospect.state=='Verified'))
    if not prospect:
        raise HTTPException(409,'Review discovery evidence before outreach.')
    evidence = json.loads(prospect.evidence)
    if now()-datetime.fromisoformat(evidence['checked_at']) > timedelta(days=7):
        raise HTTPException(409,'Website research is older than 7 days. Run discovery and verify again.')
    return evidence

def draft(db, lead, channel):
    if channel == 'whatsapp':
        raise HTTPException(409,'WhatsApp marketing templates to US numbers are currently unavailable. Use email; interested businesses can contact your WhatsApp number.')
    contact = db.scalar(select(Contact).where(Contact.business_id==lead.id))
    recipient = (contact.email if channel=='email' else contact.phone).strip() if contact else ''
    if not recipient:
        raise HTTPException(409,'A verified contact is required for this channel.')
    evidence = eligible(db,lead,recipient)
    if channel=='whatsapp' and not evidence.get('whatsapp_consent'):
        raise HTTPException(409,'Record recipient WhatsApp opt-in evidence before messaging.')
    existing = db.scalar(select(Outreach).where(Outreach.business_id==lead.id,Outreach.channel==channel))
    if existing:
        return existing
    p = prefs(db)
    name = p.get('sender_name','Opaki')
    body = (f'Hello {lead.name},\n\nI’m {name}, a website designer. While researching businesses in {lead.city}, '
        'I couldn’t find an official website for your business. If you already have one, please let me know.\n\n'
        'Would you be interested in discussing a website that presents your services and helps customers contact you?\n\n'
        f'{name}\nWhatsApp: {p.get("sender_whatsapp","")}\n\nThis is a business development advertisement.')
    row = Outreach(business_id=lead.id,channel=channel,recipient=recipient.lower() if channel=='email' else recipient,
        subject=f'Website design for {lead.name}'[:200],body=body,optout_token=secrets.token_urlsafe(32))
    db.add(row)
    db.flush()
    return row

def deliver(db, row):
    if row.channel == 'whatsapp':
        raise HTTPException(409,'WhatsApp marketing templates to US numbers are currently unavailable.')
    lead = db.get(Business,row.business_id) if row.business_id else None
    evidence = eligible(db,lead,row.recipient)
    contact = db.scalar(select(Contact).where(Contact.business_id==lead.id))
    current = contact.email.lower() if row.channel=='email' else contact.phone
    if current != row.recipient:
        raise HTTPException(409,'Contact changed. Do not send the old draft.')
    p, ready = prefs(db), readiness(db)
    if not ready[row.channel]:
        raise HTTPException(503,'Connect the sending provider in Integrations first.')
    if row.channel=='email' and (not ready['postal_address'] or settings.mail_from.lower()!=p.get('sender_email','').lower()):
        raise HTTPException(409,'Configure a full sender postal address and matching MAIL_FROM before sending.')
    if row.channel=='whatsapp' and not evidence.get('whatsapp_consent'):
        raise HTTPException(409,'WhatsApp recipient opt-in is required.')
    # The database claim is committed before the external side effect. Ambiguous outcomes
    # are never retried automatically, avoiding duplicate messages after timeouts.
    claimed = db.execute(update(Outreach).where(Outreach.id==row.id,Outreach.state=='Draft').values(state='Sending'))
    if claimed.rowcount != 1:
        raise HTTPException(409,'Already sent, sending, or awaiting delivery review.')
    db.add(Suppression(recipient=row.recipient.lower(),reason='One-time outreach claimed'))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'This recipient was already contacted or claimed by another sender.')
    try:
        if row.channel=='email':
            message=EmailMessage()
            message['Subject']=row.subject
            message['From']=settings.mail_from
            message['To']=row.recipient
            message['Reply-To']=settings.mail_from
            unsubscribe=settings.app_origin+'/api/outreach/unsubscribe/'+row.optout_token
            message['List-Unsubscribe']='<'+unsubscribe+'>'
            message.set_content(row.body+'\n\n'+p['postal_address']+'\nStop future messages: '+unsubscribe+'\nYou can also reply to opt out.')
            with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=20) as server:
                server.starttls()
                server.login(settings.smtp_user,settings.smtp_password)
                refused = server.send_message(message)
                if refused:
                    raise RuntimeError('Recipient refused')
            row.provider_id='smtp-accepted'
        else:
            data=request_json('POST',f'https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages',
                headers={'Authorization':'Bearer '+settings.whatsapp_access_token},json={'messaging_product':'whatsapp','to':row.recipient.lstrip('+'),
                'type':'template','template':{'name':settings.whatsapp_template_name,'language':{'code':'en_US'}}})
            row.provider_id=data['messages'][0]['id']
        row.state='Sent'
        row.sent_at=now()
        lead.status='Sent'
        deal=db.scalar(select(Opportunity).where(Opportunity.business_id==lead.id))
        if deal: deal.stage='Contacted'
        db.commit()
    except Exception:
        db.rollback()
        db.execute(update(Outreach).where(Outreach.id==row.id).values(state='Delivery uncertain'))
        db.commit()
        raise HTTPException(502,'Delivery could not be confirmed. Check the provider before any manual retry; automatic retries are disabled.')
    return {'state':'Sent'}

def register(app, actor, admin, audit, limit):
    @app.get('/growth')
    def overview(user=Depends(actor),db:Session=Depends(get_db)):
        return {'readiness':readiness(db),'campaign':{k:v for k,v in prefs(db).items() if k in ('postal_address','city','industry','automatic_discovery','automatic_email')},
            'prospects':[{'id':p.id,'name':p.name,'city':p.city,'industry':p.industry,'state':p.state,'business_id':p.business_id,'evidence':json.loads(p.evidence)} for p in db.scalars(select(Prospect).order_by(Prospect.created_at.desc()).limit(100))],
            'messages':[{'id':m.id,'business_id':m.business_id,'channel':m.channel,'recipient':m.recipient,'subject':m.subject,'body':m.body,'state':m.state,'response':m.response,'sent_at':m.sent_at} for m in db.scalars(select(Outreach).order_by(Outreach.created_at.desc()).limit(100))]}

    @app.put('/growth/campaign')
    def campaign(data:CampaignInput,user=Depends(admin),db:Session=Depends(get_db)):
        if data.postal_address.strip().lower() in ('uganda','usa','united states'):
            raise HTTPException(422,'Enter a full mailing address, including street or PO box and city, or leave it blank.')
        if data.automatic_email and not data.postal_address.strip():
            raise HTTPException(422,'Automatic email requires a full postal address.')
        for key,value in data.model_dump().items():
            db.merge(Preference(key=key,value=str(value).lower() if isinstance(value,bool) else value))
        audit(db,user,'campaign.updated');db.commit()
        return {'ok':True}

    def run_search(db,city,industry):
        rows,rejected=discover(city,industry)
        added=0
        for p in db.scalars(select(Prospect).where(Prospect.place_id.in_(rejected))):
            p.state='Excluded'
            lead=db.get(Business,p.business_id) if p.business_id else None
            if lead: lead.website_status='Insufficient information'
        for data in rows:
            existing=db.scalar(select(Prospect).where(Prospect.place_id==data['place_id']))
            if existing:
                # Rechecks invalidate prior human/contact review.
                if existing.state!='Dismissed':
                    existing.evidence=data['evidence'];existing.state='Review required'
                continue
            db.add(Prospect(**data));added+=1
        try: db.commit()
        except IntegrityError:
            db.rollback();raise HTTPException(409,'Another search saved these businesses. Refresh discovery.')
        return {'added':added,'excluded':len(rejected)}

    @app.post('/discovery/search')
    def search(data:SearchInput,user=Depends(admin),db:Session=Depends(get_db)):
        limit('discovery:'+user.id,10)
        result=run_search(db,data.city,data.industry)
        audit(db,user,'discovery.completed');db.commit()
        return result

    @app.post('/discovery/{id}/qualify')
    def qualify(id:str,data:QualifyInput,user=Depends(admin),db:Session=Depends(get_db)):
        p=db.get(Prospect,id)
        if not p: raise HTTPException(404,'Prospect not found')
        if p.state!='Review required': raise HTTPException(409,'Run fresh research before reviewing this prospect again.')
        if not data.confirmed_no_website: raise HTTPException(422,'Confirm the website research first.')
        if not safe_url(data.contact_source): raise HTTPException(422,'Provide the public source URL for the contact details.')
        if data.phone and not re.fullmatch(r'\+1\d{10}',data.phone): raise HTTPException(422,'Use a US phone number in +1XXXXXXXXXX format.')
        evidence=json.loads(p.evidence)
        if evidence.get('country')!='US': raise HTTPException(409,'Only US businesses qualify.')
        evidence.update(verification_note=data.verification_note,contact_source=data.contact_source,whatsapp_consent=data.whatsapp_consent,reviewed_by=user.id)
        lead=db.get(Business,p.business_id) if p.business_id else db.scalar(select(Business).where(Business.name==data.name,Business.city==p.city,Business.country=='United States'))
        if lead and (lead.website or lead.status in ('Do not contact','Not interested','Sent','Replied','Interested','Converted')):
            raise HTTPException(409,'Existing business has a website, was contacted, or is suppressed.')
        if not lead:
            lead=Business(name=data.name,country='United States',city=p.city,industry=p.industry,description=data.verification_note,source='Google Places + web review')
            db.add(lead);db.flush();db.add(Contact(business_id=lead.id));db.add(Opportunity(business_id=lead.id));db.flush()
        lead.website_status='No official website found';lead.status='Qualified'
        contact=db.scalar(select(Contact).where(Contact.business_id==lead.id))
        contact.email=str(data.email or '').lower();contact.phone=data.phone
        p.business_id=lead.id;p.state='Verified';p.evidence=json.dumps(evidence)
        audit(db,user,'prospect.verified',p.id);db.commit()
        return {'business_id':lead.id}

    @app.post('/outreach/draft')
    def make_draft(data:DraftInput,user=Depends(admin),db:Session=Depends(get_db)):
        lead=db.get(Business,data.business_id)
        if not lead: raise HTTPException(404,'Business not found')
        try:
            row=draft(db,lead,data.channel);audit(db,user,'outreach.drafted',row.id);db.commit()
        except IntegrityError:
            db.rollback();raise HTTPException(409,'A draft already exists. Refresh outreach.')
        return {'id':row.id}

    @app.post('/outreach/{id}/send')
    def send(id:str,user=Depends(admin),db:Session=Depends(get_db)):
        limit('outreach:workspace',20)
        row=db.get(Outreach,id)
        if not row: raise HTTPException(404,'Message not found')
        result=deliver(db,row);audit(db,user,'outreach.sent',id);db.commit();return result

    @app.post('/outreach/{id}/reply')
    def reply(id:str,data:ReplyInput,user=Depends(admin),db:Session=Depends(get_db)):
        row=db.get(Outreach,id)
        if not row: raise HTTPException(404,'Message not found')
        row.response=data.body;row.state='Replied'
        db.merge(Suppression(recipient=row.recipient.lower(),reason='Opt out' if data.stop else 'Replied'))
        lead=db.get(Business,row.business_id) if row.business_id else None
        if lead: lead.status='Do not contact' if data.stop else 'Replied'
        audit(db,user,'outreach.reply_recorded',id);db.commit();return {'ok':True}

    @app.get('/outreach/unsubscribe/{token}',response_class=HTMLResponse)
    def unsubscribe_page(token:str):
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,100}',token): raise HTTPException(404)
        return '<h1>Stop messages from Opaki</h1><form method="post"><button>Unsubscribe</button></form>'

    @app.post('/outreach/unsubscribe/{token}',response_class=HTMLResponse)
    def unsubscribe(token:str,db:Session=Depends(get_db)):
        row=db.scalar(select(Outreach).where(Outreach.optout_token==token))
        if not row: raise HTTPException(404,'Link not found')
        db.merge(Suppression(recipient=row.recipient.lower(),reason='Opt out'))
        lead=db.get(Business,row.business_id) if row.business_id else None
        if lead: lead.status='Do not contact'
        db.commit()
        return '<h1>You are unsubscribed.</h1><p>No further outreach will be sent to this address.</p>'

    @app.get('/growth/run')
    def scheduled(request:Request,db:Session=Depends(get_db)):
        if not settings.cron_secret or not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+settings.cron_secret):
            raise HTTPException(401,'Scheduler authorization required')
        limit('growth:scheduled',1)
        p=prefs(db);result={}
        sent=0
        if p.get('automatic_email')=='true':
            for prospect in db.scalars(select(Prospect).where(Prospect.state=='Verified').limit(20)).all():
                lead=db.get(Business,prospect.business_id) if prospect.business_id else None
                if not lead: continue
                try:
                    row=draft(db,lead,'email');db.commit()
                    if row.state=='Draft': deliver(db,row);sent+=1
                except HTTPException: db.rollback()
                if sent>=5: break
        if p.get('automatic_discovery')=='true': result['discovery']=run_search(db,p.get('city','Austin, Texas'),p.get('industry','barbers'))
        return {**result,'sent':sent}
