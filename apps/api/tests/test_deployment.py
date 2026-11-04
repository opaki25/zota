import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.config import Settings

def test_vercel_requires_explicit_services_and_secure_settings():
    with pytest.raises(ValidationError, match='requires explicit'):
        Settings(_env_file=None, vercel_env='production')
    values = dict(vercel_env='production', database_url='postgresql+psycopg://user:pass@db.test/zota', redis_url='rediss://cache.test:6379/0', app_origin='https://studio.test', secure_cookies=True, testing=False)
    assert Settings(_env_file=None, **values).secure_cookies
    for overrides in ({'database_url': 'sqlite:///./zota.db'}, {'secure_cookies': False}, {'testing': True}, {'app_origin': 'http://localhost:3000'}):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **(values | overrides))

def test_docs_use_public_prefix_while_backend_routes_remain_unprefixed():
    app = FastAPI(root_path='/api')
    @app.get('/health')
    def health():
        return {'status': 'ok'}
    client = TestClient(app)
    assert client.get('/health').json() == {'status': 'ok'}
    assert '/api/openapi.json' in client.get('/docs').text
    assert client.get('/openapi.json').json()['servers'] == [{'url': '/api'}]
