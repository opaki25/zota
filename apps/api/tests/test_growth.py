import json
from datetime import timedelta
import pytest
from sqlalchemy import select
from app import growth
from app.config import settings
from app.models import Business, Contact, Opportunity, Prospect, Preference, Outreach, Suppression, now
from test_workflows import client, signin

def verified(client,**values):
    with client.factory() as db:
        lead=Business(name='Fictional Barber',country='United States',city='Austin, Texas',industry='barbers',website_status='No official website found',status='Qualified',**values)
        db.add(lead);db.flush()
        db.add(Contact(business_id=lead.id,email='test@example.com',phone='+15125550100'))
        db.add(Opportunity(business_id=lead.id))
        db.add(Prospect(place_id='test-place',name=lead.name,city=lead.city,industry=lead.industry,business_id=lead.id,state='Verified',evidence=json.dumps({'country':'US','checked_at':now().isoformat(),'whatsapp_consent':'Test consent'})))
        for key,value in {'sender_email':'sender@example.com','sender_name':'Opaki','postal_address':'Test PO Box 123, Kampala, Uganda'}.items():
            db.add(Preference(key=key,value=value))
        db.commit();return lead.id

def test_growth_requires_auth_and_admin(client):
    assert client.get('/growth').status_code==401
    signin(client,'viewer@example.com')
    assert client.get('/growth').status_code==200
    assert client.post('/discovery/search',json={'city':'Austin, Texas','industry':'barbers'}).status_code==403
    assert client.get('/growth/run').status_code==401

def test_missing_keys_does_not_return_fake_leads(client,monkeypatch):
    monkeypatch.setattr(settings,'google_places_api_key','')
    signin(client)
    assert client.post('/discovery/search',json={'city':'Austin, Texas','industry':'barbers'}).status_code==503
    assert client.get('/growth').json()['prospects']==[]

def test_discovery_excludes_foreign_websites_ambiguous_and_empty(monkeypatch):
    monkeypatch.setattr(settings,'google_places_api_key','test')
    monkeypatch.setattr(settings,'brave_search_api_key','test')
    def place(id,country='US',website=''):
        return {'id':id,'displayName':{'text':id},'businessStatus':'OPERATIONAL','addressComponents':[{'types':['country'],'shortText':country}],'websiteUri':website}
    calls=[]
    def provider(method,url,**kw):
        calls.append(url)
        if method=='POST': return {'places':[place('foreign','UG'),place('website',website='https://official.test'),place('unknown'),place('empty'),place('candidate')]}
        query=kw['params']['q']
        if 'unknown' in query:return {'web':{'results':[{'url':'https://possible-official.test'}]}}
        if 'empty' in query:return {'web':{'results':[]}}
        return {'web':{'results':[{'url':'https://www.facebook.com/test','title':'Business'}]}}
    monkeypatch.setattr(growth,'request_json',provider)
    results,rejected=growth.discover('Austin, Texas','barbers')
    assert len(results)==1 and results[0]['place_id']=='candidate'
    assert len(rejected)==4 and len(calls)==4

def test_draft_blocks_existing_site_and_us_whatsapp(client):
    signin(client);id=verified(client,website='https://official.test')
    assert client.post('/outreach/draft',json={'business_id':id,'channel':'email'}).status_code==409
    assert client.post('/outreach/draft',json={'business_id':id,'channel':'whatsapp'}).status_code==409

def test_send_once_optout_and_public_confirmation(client,monkeypatch):
    signin(client);id=verified(client)
    for key,value in {'smtp_host':'smtp.test','smtp_user':'sender@example.com','smtp_password':'test','mail_from':'sender@example.com'}.items():monkeypatch.setattr(settings,key,value)
    sent=[]
    class SMTP:
        def __init__(self,*a,**kw): pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def starttls(self):pass
        def login(self,*a):pass
        def send_message(self,message):sent.append(message);return {}
    monkeypatch.setattr(growth.smtplib,'SMTP',SMTP)
    first=client.post('/outreach/draft',json={'business_id':id,'channel':'email'}).json()['id']
    assert client.post('/outreach/draft',json={'business_id':id,'channel':'email'}).json()['id']==first
    assert client.post(f'/outreach/{first}/send').status_code==200
    assert client.post(f'/outreach/{first}/send').status_code==409
    assert len(sent)==1 and 'unsubscribe' in sent[0].get_content()
    with client.factory() as db:token=db.get(Outreach,first).optout_token
    client.headers.pop('Origin');client.headers.pop('X-CSRF-Token');client.cookies.clear()
    assert client.get('/outreach/unsubscribe/'+token).status_code==200
    assert client.post('/outreach/unsubscribe/'+token).status_code==200
    with client.factory() as db:
        assert db.get(Suppression,'test@example.com').reason=='Opt out'
        assert db.get(Business,id).status=='Do not contact'

def test_stale_evidence_and_country_only_address(client):
    signin(client);id=verified(client)
    with client.factory() as db:
        p=db.scalar(select(Prospect));p.evidence=json.dumps({'country':'US','checked_at':(now()-timedelta(days=8)).isoformat()});db.commit()
    assert client.post('/outreach/draft',json={'business_id':id,'channel':'email'}).status_code==409
    assert client.put('/growth/campaign',json={'postal_address':'Uganda'}).status_code==422

def test_failed_send_is_not_retried(client,monkeypatch):
    signin(client);id=verified(client)
    for key,value in {'smtp_host':'smtp.test','smtp_user':'sender@example.com','smtp_password':'test','mail_from':'sender@example.com'}.items():monkeypatch.setattr(settings,key,value)
    def fail(*a,**kw):raise TimeoutError()
    monkeypatch.setattr(growth.smtplib,'SMTP',fail)
    row=client.post('/outreach/draft',json={'business_id':id,'channel':'email'}).json()['id']
    assert client.post(f'/outreach/{row}/send').status_code==502
    assert client.post(f'/outreach/{row}/send').status_code==409
    with client.factory() as db:assert db.get(Outreach,row).state=='Delivery uncertain'
