# Vercel multi-service deployment

## Deployment topology

The root `vercel.json` declares **web** (Next.js, `apps/web`) and **api** (FastAPI, `apps/api`, entrypoint `app.main:app`). The public catch-all routes to **web**. **api** has no direct public rewrite and is reached by **web** through its `API_SERVICE_URL` binding.

Public requests follow this path:

```text
/                  -> web -> dashboard
/api/auth/login    -> web route handler -> api /auth/login
/api/leads         -> web route handler -> api /leads
/api/export        -> web route handler -> api /export
/api/docs          -> web route handler -> api /docs
/api/openapi.json  -> web route handler -> api /openapi.json
```

“Internal api” means no separate direct Vercel ingress. API endpoints remain accessible through the public web proxy and retain backend authentication/authorization checks. The proxy is not an additional authentication boundary.

This differs from the suggested direct `/api/* -> api` rewrite intentionally: the application already uses a same-origin web-to-API proxy, and a runtime route handler gives that existing relationship a real service binding. Vercel's public service rewrites preserve the request path; the Next handler explicitly removes the `/api` prefix. A `destination.path` alone would not strip the path seen by FastAPI. The browser URLs stay unchanged.

The binding is read inside a Node.js route function on each request. It is not read in `next.config.ts`, at build time, in middleware, or in client code. Vercel creates `API_SERVICE_URL`; **do not set it in Project Settings or environment files**. Standalone Next/Docker uses the separate `LOCAL_API_URL`. A Vercel deployment with a missing binding returns 503 rather than falling back to localhost.

## Project setup

1. Import `opaki25/zota` as one multi-service project with the **repository root** as its root directory. Do not select only `apps/web`.
2. Keep the configured `web` public ingress and `web -> api` runtime binding. Vercel supplies the binding URL automatically.
3. Configure the values in `.env.vercel.example` separately for Preview and Production. Never commit real credentials.
4. Supply a hosted PostgreSQL database and a Redis service that supports the Redis wire protocol (`redis://` or `rediss://`), not just a REST endpoint. Docker hostnames `postgres` and `redis` do not exist on Vercel. Use a provider-supported pooled PostgreSQL URL and TLS settings; SQLAlchemy here requires the `postgresql+psycopg://` scheme.
5. Set `APP_ORIGIN` to the exact browser origin, with no trailing slash (for example, your chosen HTTPS domain). Use an explicit preview origin for preview login/reset testing. It is deliberately not inferred from an incoming Host header. Set `SECURE_COOKIES=true` and `API_ROOT_PATH=/api`. Never set `TESTING=true` on Vercel.
6. From a trusted environment with that database's connection variables, run `cd apps/api`, `alembic upgrade head`, then `python -m app.manage YOUR_EMAIL`. The CLI asks for the administrator password privately. Migrations and account creation are **not** run during a build or cold start; previews must not mutate the production database.
7. Deploy after local/build checks and environment configuration. Test `/api/health`, login/logout, lead creation, notes, reminders, `/api/export`, and `/api/docs` on the deployed origin.

Python is pinned to 3.12 using `apps/api/.python-version`. Vercel's detected `requirements.txt` includes the tested lockfile. The root npm workspace/lockfile remains the source for web dependencies. Neither service requires a custom top-level build command.

The web service explicitly installs development and optional dependencies using `npm ci`. Lightning CSS and Tailwind Oxide require platform-specific native packages. Regenerate the lockfile in a clean directory containing the workspace manifests, without an existing `node_modules` tree, so Windows does not omit the Linux packages used by Vercel. Direct web dependency versions are pinned. Run `node scripts/check-native-dependencies.mjs --lock-only` to verify all native variants are recorded, and omit `--lock-only` after installation to load and exercise the native modules on the current platform. Ubuntu CI runs both checks before the production build.

## Local service testing

Install Node/npm, Python 3.12, the project dependencies, and a current Vercel CLI with Services support. Activate `.venv` and make the Python runtime available to the CLI. Provide local PostgreSQL/Redis (or isolated hosted development resources), apply migrations, and create an account first. Export API environment settings into the shell used for the command, including `APP_ORIGIN=http://localhost:3000`, `SECURE_COOKIES=false`, and `API_ROOT_PATH=/api`.

Run from the repository root:

```sh
vercel dev -L --listen localhost:3000
```

`vercel dev` also works with a linked project. Both modes inject the service binding; never define it manually. When selecting a different local port or hostname, change `APP_ORIGIN` to match it exactly. Verify `/api/health`, authenticated CRUD, cookies after login/logout, and the schema link in `/api/docs`.

For standalone `npm run dev`, the proxy defaults to `http://127.0.0.1:8000`. To override it, put `LOCAL_API_URL` in `apps/web/.env.local`; this variable is only a non-Vercel fallback. Docker Compose supplies `LOCAL_API_URL=http://api:8000` at runtime. No rebuild is required to change this local runtime address.

## PostgreSQL, Redis, and Celery

PostgreSQL/Redis are external infrastructure, not HTTP Vercel services. No new provider account or database is provisioned by this change. The existing Celery worker has only a health task and is omitted from this deployment. Keep Docker/worker hosting separately if needed. If continuous queue processing is required later, configure a Vercel daemon or an external worker explicitly; do not declare the Celery process as an HTTP service. The Phase 1 worker is intentionally not deployed by this configuration.

## Validation

```sh
node --experimental-strip-types --test scripts/api-proxy.test.mjs
npm run typecheck
npm run build
cd apps/api
python -m pytest tests -q
```

The proxy tests exercise actual HTTP forwarding, cookies, public-origin/CSRF preservation, downloads, redirects, binding failures, and routing configuration. Deployment tests cover required Vercel environment settings and OpenAPI's public prefix. Local tests do not prove that Vercel service resolution or the hosted database works; the `vercel dev` and deployed smoke tests are separate checks.

Authoring-environment results: 14 Python tests and 5 Node proxy tests pass. The configuration passes field validation against the downloaded Vercel schema, including a negative check for a missing binding field. The published schema has an unrelated draft/schema-metadata inconsistency; field validation used a Draft 7 validator. `vercel dev` was attempted but could not start: npm first failed with a cache-lock error, and an isolated CLI installation then failed with a registry idle timeout. A frontend dependency-repair attempt also stalled and was stopped. The existing missing Next.js declaration files prevent a complete typecheck/build; no type errors were suppressed. Vercel runtime integration, hosted infrastructure, and a full frontend build are not verified. The selected topology is public web ingress with a private API binding; PostgreSQL and Redis are supplied externally.

## Official references

- [Services](https://vercel.com/docs/services)
- [Service routing and path semantics](https://vercel.com/docs/services/routing)
- [Bindings and runtime restrictions](https://vercel.com/docs/services/bindings)
- [FastAPI deployment](https://vercel.com/docs/frameworks/backend/fastapi)
