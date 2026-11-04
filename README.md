# Zota

A business development workspace for an independent website studio. **Phase 1 implementation**: Next.js / TypeScript frontend, FastAPI backend, SQLAlchemy database, Alembic migration, Redis authentication rate limiting, and Celery worker infrastructure.

## Implemented

- Administrator sign-in/sign-out with Argon2 password hashing, opaque server-side sessions, HTTP-only cookies, CSRF tokens, strict mutation Origin checks, expiration, and revocation.
- Password recovery through configured SMTP; single-use reset tokens expire after 30 minutes and revoke all existing sessions.
- Admin, editor, and viewer roles; team accounts created through the administrative CLI.
- Persistent business records, contacts, manual website classifications, CRM stages, estimated USD deal values, research notes, and internal follow-up reminders.
- Uganda exclusion on lead input, CSV import, and configured target markets.
- Atomic CSV import, duplicate constraints, CSV export with spreadsheet formula escaping.
- Dashboard metrics and pipeline chart based on stored records; search and country/industry/status filters.
- Settings and administrator audit log. Do-not-contact and declined leads cannot receive new reminders; existing reminders are closed.
- Responsive UI, real empty states, error reporting, and clearly marked future integration screens. No fabricated prospects or demo records are seeded.

## Architecture

`apps/web` is a Next.js App Router application using Tailwind, Lucide, and a shadcn-style Radix/CVA Button primitive. The browser calls same-origin `/api/*`; a Next Node.js route handler forwards requests to FastAPI using the runtime service binding on Vercel (or LOCAL_API_URL locally). Only the backend accesses PostgreSQL and provider secrets. `apps/api/app` contains authentication, schema validation, persistence, CRM endpoints, and the worker entry point. Alembic owns schema initialization; the app never silently creates tables on startup.

PostgreSQL is the deployment database. SQLite is supported for isolated development and unit tests, not as a production substitute. Redis must be available for login/recovery rate limiting; failure is closed with HTTP 503. Celery is scaffolded with a health task only; there are no discovery or delivery jobs yet.

## Vercel deployment

The root `vercel.json` configures one public `web` service and an internal `api` service connected by a runtime binding. Browser API paths stay at `/api/*`. See [Vercel configuration and setup](docs/vercel.md) and `.env.vercel.example`. This repository configuration does not provision external databases or create a Vercel deployment. Configure the documented environment values when importing the repository.

## Quick start with Docker

Install Docker with Compose and copy `.env.example` to `.env`. Replace the example database password with a long random URL-safe value. Keep `.env` outside source control.

```sh
docker compose up --build -d
docker compose exec api python -m app.manage you@yourstudio.com
```

The account CLI prompts privately for a password of at least 12 characters. No default account or password is provided. Open http://localhost:3000. API documentation is at http://localhost:3000/api/docs when API_ROOT_PATH=/api. Use the same hostname configured in `APP_ORIGIN`; `localhost` and `127.0.0.1` are different origins.

Add a team member with `docker compose exec api python -m app.manage editor@example.com --role editor` (or `viewer`). All users share the studio workspace; this is not a multi-tenant product.

## Local development

Requires Node 24 with npm, Python 3.12+, PostgreSQL, and Redis. Run database and Redis using Compose, or install them separately.

```sh
npm ci
python -m venv .venv
# Activate the virtual environment for your shell.
pip install -r apps/api/requirements-lock.txt
docker compose up postgres redis -d
cd apps/api
# Copy the root .env into this directory for local API commands, or export its variables.
alembic upgrade head
python -m app.manage you@yourstudio.com
uvicorn app.main:app --reload
```

In another terminal from the repository root, run `npm run dev`. Visit **http://localhost:3000**. For an isolated SQLite development database set `DATABASE_URL=sqlite:///./zota.db`; Redis is still required outside tests. Set `SECURE_COOKIES=false` only for local HTTP. FastAPI reads `.env` from the current working directory; Compose injects the root file automatically.

## Tests and checks

```sh
node --experimental-strip-types --test scripts/api-proxy.test.mjs
npm run typecheck
npm run build
cd apps/api
python -m pytest tests -q
alembic upgrade head
alembic check
```

The API suite covers access control, CSRF, origin rejection, session expiry/logout, single-use password reset, session revocation, CRM persistence, declined-lead reminders, excluded countries, atomic duplicate imports, and formula-safe exports. Tests use an isolated in-memory database and disable only Redis rate limiting. Never set `TESTING=true` in a deployed environment.

**Validation status in the authoring environment:** All 14 API/deployment tests and 5 Node proxy tests pass. Python syntax/source checks pass. The initial Alembic migration runs on SQLite and `alembic check` reports no schema drift. Backend dependencies are pinned in `requirements-lock.txt`; frontend dependencies are recorded in `package-lock.json` (generated from cached package metadata). Frontend installation failed with a network connection reset; its retry stalled and a separate request to the Next.js package URL timed out. The stalled installer was stopped. Next.js successfully compiled the frontend source, then failed its TypeScript stage because the interrupted install omitted Next.js declaration files (`next` and `next/types.js`). TypeScript configuration issues found during checks were fixed. A complete production build and browser verification remain outstanding; dependency errors have not been hidden with stubs or disabled type checks. Retry `npm ci` when registry access is working, then run the checks above. PostgreSQL and Docker execution are not verified because those runtimes are unavailable here. No production-readiness claim is made.

## CSV format

UTF-8 CSV with a header and 1–1000 records, maximum 500 KB:

```csv
name,country,city,industry,description,website,email,phone
```

`name`, `country`, and `industry` are required. Contacts and website are optional. Use full country names consistently. A website URL must begin with `http://` or `https://`. Imports are atomic; a duplicate name/country/city rolls back the entire batch. Exported formula-like values are prefixed with an apostrophe; review these prefixes if reimporting.

## Remaining phases

2. Approved discovery adapters, source provenance, provider limits, scheduling, and real Google Places/search discovery.
3. Evidence-backed website verification (including social-link separation), confidence and timestamp storage, OpenAI structured qualification, configurable weights.
4. Draft versions, channel-specific AI messages, human editing/approval/rejection, and duplicate-outreach safeguards.
5. Authorized TikTok OAuth, WhatsApp eligibility/templates/consent/windows, email delivery, signature-verified webhooks, inbox, response classification, and suppression across imports and channels.
6. Scheduled job controls, retries/logs/usage, richer analytics and date/score filters, quotations, notifications, retention policies, end-to-end tests, and deployment hardening.

The current integration screens are explicit placeholders, not working adapters. Website classifications are manual and have no automated evidence claims. Outreach-related lead statuses are manual CRM labels; they do not prove a message was sent. No outbound sending capability exists in Phase 1.

See [deployment guidance](docs/deployment.md), [integration setup](docs/integrations.md), and [schema/API notes](docs/architecture.md).
