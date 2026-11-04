import { proxyApi } from '../../../lib/api-proxy';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type Context = { params: Promise<{ path?: string[] }> };

async function handle(request: Request, context: Context): Promise<Response> {
  const { path = [] } = await context.params;
  return proxyApi(request, path);
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE, handle as OPTIONS, handle as HEAD };
