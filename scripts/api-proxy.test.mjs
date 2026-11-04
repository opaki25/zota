import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { apiBaseUrl, proxyApi } from '../apps/web/lib/api-proxy.ts';

test('Vercel binding wins and is resolved per request; no localhost fallback on Vercel', () => {
  assert.equal(apiBaseUrl({ API_SERVICE_URL: 'https://bound.test/base', LOCAL_API_URL: 'http://local.test' }).href, 'https://bound.test/base/');
  assert.equal(apiBaseUrl({ API_SERVICE_URL: 'https://preview.test' }).hostname, 'preview.test');
  assert.throws(() => apiBaseUrl({ VERCEL: '1', LOCAL_API_URL: 'http://local.test' }));
  assert.equal(apiBaseUrl({ LOCAL_API_URL: 'http://api:8000' }).href, 'http://api:8000/');
});

test('forwards POST body, public Origin, CSRF and cookies over a real HTTP connection', async () => {
  let received;
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    received = { path: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() };
    res.writeHead(201, {
      'Content-Type': 'application/json',
      'Set-Cookie': ['zota_session=test; HttpOnly; Path=/; SameSite=Lax', 'other=test; Path=/'],
    });
    res.end('{"ok":true}');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const request = new Request('https://studio.test/api/leads?country=Kenya', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Cookie: 'zota_session=existing', Origin: 'https://studio.test', 'X-CSRF-Token': 'csrf', 'X-Forwarded-Host': 'attacker.test' },
      body: '{"name":"Test business"}',
    });
    const response = await proxyApi(request, ['leads'], { API_SERVICE_URL: `http://127.0.0.1:${server.address().port}` });
    assert.equal(response.status, 201);
    assert.deepEqual(await response.json(), { ok: true });
    assert.equal(received.path, '/leads?country=Kenya');
    assert.equal(received.body, '{"name":"Test business"}');
    assert.equal(received.headers.origin, 'https://studio.test');
    assert.equal(received.headers.cookie, 'zota_session=existing');
    assert.equal(received.headers['x-csrf-token'], 'csrf');
    assert.equal(received.headers['x-forwarded-host'], undefined);
    assert.equal(response.headers.getSetCookie().length, 2);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});

test('preserves logout cookies, CSV download headers, errors and redirects', async () => {
  const request = new Request('https://studio.test/api/export');
  const env = { API_SERVICE_URL: 'https://api.internal/base/' };
  const csv = await proxyApi(request, ['export'], env, async () => new Response('name\nTest', {
    headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename=leads.csv', 'Set-Cookie': 'zota_session=""; Max-Age=0; Path=/' },
  }));
  assert.equal(csv.headers.get('Content-Disposition'), 'attachment; filename=leads.csv');
  assert.match(csv.headers.get('Set-Cookie'), /Max-Age=0/);
  assert.equal(await csv.text(), 'name\nTest');
  const redirect = await proxyApi(request, ['leads'], env, async () => new Response(null, { status: 307, headers: { Location: 'https://api.internal/base/leads/?page=2' } }));
  assert.equal(redirect.headers.get('Location'), '/api/leads/?page=2');
  const prefixed = await proxyApi(request, ['leads'], env, async () => new Response(null, { status: 307, headers: { Location: 'https://api.internal/api/leads/' } }));
  assert.equal(prefixed.headers.get('Location'), '/api/leads/');
  const auth = await proxyApi(request, ['leads'], env, async () => Response.json({ detail: 'Sign in' }, { status: 401 }));
  assert.equal(auth.status, 401);
  assert.deepEqual(await auth.json(), { detail: 'Sign in' });
});

test('fails safely for missing bindings, transport failures and path escape attempts', async () => {
  const request = new Request('https://studio.test/api/leads');
  assert.equal((await proxyApi(request, ['leads'], { VERCEL: '1' })).status, 503);
  const env = { API_SERVICE_URL: 'https://internal.test' };
  const failure = await proxyApi(request, ['leads'], env, async () => { throw new Error('secret internal hostname'); });
  assert.equal(failure.status, 502);
  assert.doesNotMatch(await failure.text(), /secret|internal\.test/);
  for (const path of [['..'], ['//attacker.test'], ['a/b'], ['a\\b']]) {
    assert.equal((await proxyApi(request, path, env)).status, 400);
  }
  const redirect = await proxyApi(request, ['leads'], env, async () => new Response(null, { status: 302, headers: { Location: 'https://attacker.test' } }));
  assert.equal(redirect.status, 502);
});

test('service ingress and caller binding match the runtime route', async () => {
  const config = JSON.parse(await readFile(new URL('../vercel.json', import.meta.url)));
  assert.deepEqual(Object.keys(config.services).sort(), ['api', 'web']);
  assert.equal(config.services.api.entrypoint, 'app.main:app');
  assert.deepEqual(config.services.web.bindings, [{ type: 'service', service: 'api', format: 'url', env: 'API_SERVICE_URL' }]);
  assert.deepEqual(config.rewrites, [{ source: '/(.*)', destination: { service: 'web' } }]);
});
