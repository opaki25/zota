from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app, passwords, digest
from app.models import User, Session, Business, Recovery, now

@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add(User(email='admin@example.com', password_hash=passwords.hash('long-test-password'), role='admin'))
        db.add(User(email='viewer@example.com', password_hash=passwords.hash('long-test-password'), role='viewer'))
        db.commit()
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app, headers={'Origin':'http://localhost:3000'}) as client:
        client.factory = factory
        yield client
    app.dependency_overrides.clear()
    engine.dispose()

def signin(client, email='admin@example.com'):
    result = client.post('/auth/login', json={'email':email,'password':'long-test-password'})
    assert result.status_code == 200
    client.headers['X-CSRF-Token'] = result.json()['csrf']

def lead(**overrides):
    return {'name':'Fictional Test Studio','country':'Kenya','city':'Nairobi','industry':'Design', **overrides}

def test_auth_csrf_and_logout(client):
    assert client.get('/leads').status_code == 401
    signin(client)
    token = client.headers.pop('X-CSRF-Token')
    assert client.post('/leads',json=lead()).status_code == 403
    client.headers['X-CSRF-Token'] = token
    assert client.post('/auth/logout').status_code == 200
    assert client.get('/leads').status_code == 401

def test_origin_rejected(client):
    assert client.post('/auth/login', headers={'Origin':'https://attacker.test'},json={'email':'admin@example.com','password':'long-test-password'}).status_code == 403

def test_viewer_cannot_mutate(client):
    signin(client,'viewer@example.com')
    assert client.get('/leads').status_code == 200
    assert client.post('/leads',json=lead()).status_code == 403
    assert client.get('/audit').status_code == 403

def test_crm_lifecycle_and_suppression(client):
    signin(client)
    result = client.post('/leads',json=lead())
    assert result.status_code == 201
    business = result.json()
    reminder = {'business_id':business['id'],'body':'Review research','due_at':(now()+timedelta(days=2)).isoformat()+'Z'}
    assert client.post('/follow-ups',json=reminder).status_code == 201
    assert client.post(f"/leads/{business['id']}/notes",json={'body':'Confirmed public business details'}).status_code == 201
    business.update(status='Do not contact',stage='Lost',value=1200)
    assert client.put(f"/leads/{business['id']}",json=business).status_code == 200
    assert client.get('/follow-ups').json()[0]['done'] is True
    assert client.post('/follow-ups',json=reminder).status_code == 409
    assert client.delete(f"/leads/{business['id']}").status_code == 200
    assert client.get('/leads').json() == []
    assert len(client.get('/audit').json()) >= 5

@pytest.mark.parametrize('country',['Uganda',' ug ','UGA'])
def test_excluded_country(client,country):
    signin(client)
    assert client.post('/leads',json=lead(country=country)).status_code == 422

def test_csv_atomic_duplicates_and_injection(client):
    signin(client)
    content='name,country,city,industry\nTest Ltd,Kenya,Nairobi,Design\nTest Ltd,Kenya,Nairobi,Design\n'
    assert client.post('/leads/import',json={'content':content}).status_code == 409
    assert client.get('/leads').json() == []
    assert client.post('/leads',json=lead(name='=HYPERLINK("bad")')).status_code == 201
    assert "'=HYPERLINK" in client.get('/export').text

def test_session_expiry(client):
    signin(client)
    with client.factory() as db:
        session = db.scalar(select(Session))
        session.expires_at = now()-timedelta(seconds=1)
        db.commit()
    assert client.get('/auth/me').status_code == 401

def test_new_deal_value_and_validation(client):
    signin(client)
    created = client.post('/leads', json=lead(value=1750, stage='Quotation'))
    assert created.status_code == 201
    assert created.json()['value'] == 1750
    assert created.json()['stage'] == 'Quotation'
    assert client.post('/leads', json=lead(website='javascript:alert(1)')).status_code == 422
    assert client.post('/leads', json=lead(name='   ')).status_code == 422
    assert client.post('/leads', json=lead(value=-1)).status_code == 422

def test_reminder_timezone_and_settings(client):
    signin(client)
    business = client.post('/leads', json=lead()).json()
    data = {'business_id':business['id'], 'body':'Call reminder', 'due_at':'2027-01-01T12:00:00+03:00'}
    result = client.post('/follow-ups', json=data)
    assert result.status_code == 201
    assert result.json()['due_at'].startswith('2027-01-01T09:00:00')
    data['due_at'] = '2027-01-01T12:00:00'
    assert client.post('/follow-ups', json=data).status_code == 422
    assert client.put('/settings',json={'business_name':'Studio','sender_name':'Owner','target_countries':'Kenya, ug'}).status_code == 422

def test_password_reset_revokes_sessions_and_is_single_use(client):
    signin(client)
    token = 'test-reset-token-that-is-long-enough'
    with client.factory() as db:
        user = db.scalar(select(User).where(User.email=='admin@example.com'))
        db.add(Recovery(user_id=user.id,token_hash=digest(token),expires_at=now()+timedelta(minutes=5)))
        db.commit()
    data={'token':token,'password':'another-long-password'}
    assert client.post('/auth/reset',json=data).status_code == 200
    assert client.get('/auth/me').status_code == 401
    assert client.post('/auth/reset',json=data).status_code == 400
