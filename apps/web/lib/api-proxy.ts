type Environment = Record<string, string | undefined>;

// Called inside a Node.js route handler, never during a build or in middleware.
export function apiBaseUrl(env: Environment = process.env): URL {
  const bound = env.API_SERVICE_URL;
  const vercel = env.VERCEL === '1' || ['production', 'preview'].includes(env.VERCEL_ENV || '');
  const base = bound || (vercel ? undefined : env.LOCAL_API_URL || 'http://127.0.0.1:8000');
  if (!base) throw new Error('The api service binding is missing');
  const url = new URL(base.endsWith('/') ? base : base + '/');
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Invalid API base URL');
  }
  return url;
}

function failure(detail: string, status: number): Response {
  return Response.json({ detail }, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function proxyApi(
  request: Request,
  path: string[],
  env: Environment = process.env,
  send: typeof fetch = fetch,
): Promise<Response> {
  // Each segment must stay inside the bound service; no user-supplied hostnames.
  if (path.some(segment => !segment || segment === '.' || segment === '..' || /[\\/]/.test(segment))) {
    return failure('Invalid API path', 400);
  }
  let base: URL;
  try { base = apiBaseUrl(env); }
  catch { return failure('The API connection is not configured', 503); }
  const target = new URL(path.map(encodeURIComponent).join('/'), base);
  target.search = new URL(request.url).search;

  const headers = new Headers();
  for (const name of ['accept', 'content-type', 'cookie', 'origin', 'x-csrf-token']) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  try {
    const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > 1_000_000) return failure('Request too large', 413);
    const upstream = await send(target, {
      method: request.method,
      headers,
      body,
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(30_000),
    });
    const outgoing = new Headers();
    for (const name of ['content-type', 'content-disposition', 'retry-after', 'www-authenticate', 'x-content-type-options', 'x-frame-options']) {
      const value = upstream.headers.get(name);
      if (value !== null) outgoing.set(name, value);
    }
    outgoing.set('Cache-Control', 'no-store');
    // Keep login and logout cookies separate; never fold Set-Cookie values.
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append('Set-Cookie', cookie);
    const location = upstream.headers.get('location');
    if (location) {
      const redirect = new URL(location, target);
      if (redirect.origin !== base.origin) {
        return failure('Unexpected API redirect', 502);
      }
      // FastAPI may already include its configured public root_path.
      const publicPath = redirect.pathname === '/api' || redirect.pathname.startsWith('/api/')
        ? redirect.pathname
        : redirect.pathname.startsWith(base.pathname)
          ? '/api/' + redirect.pathname.slice(base.pathname.length)
          : null;
      if (!publicPath) return failure('Unexpected API redirect', 502);
      outgoing.set('Location', publicPath + redirect.search + redirect.hash);
    }
    return new Response(request.method === 'HEAD' ? null : upstream.body, {
      status: upstream.status,
      headers: outgoing,
    });
  } catch {
    // Do not disclose internal binding URLs, provider errors, or credentials.
    return failure('The API is temporarily unavailable', 502);
  }
}
