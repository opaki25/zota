# Deployment and operations

This is a Phase 1 implementation with 14 passing API/deployment tests and 5 passing Node proxy tests and a verified SQLite migration/schema comparison. Vercel frontend compilation and TypeScript checks passed at commit d25059a. The complete multi-service deployment, browser checks, PostgreSQL, and Docker verification remain outstanding. Do not expose it publicly until builds/tests, PostgreSQL migration checks, and a staging authentication walkthrough pass.

## Vercel

See [Vercel multi-service deployment](vercel.md) for the service topology, required environment values, external databases, and local `vercel dev` testing.

## Docker deployment path

1. Install and lock frontend/backend dependencies; run the documented test suite and build.
2. Provision PostgreSQL and Redis on a private network. Use managed backups and encrypted transport where available.
3. Configure `.env` or a secrets manager. Use a URL-safe database password (or percent-encode it in a separately supplied SQLAlchemy URL). Never prefix secret variables with `NEXT_PUBLIC_`.
4. Build both images. Compose supplies `LOCAL_API_URL=http://api:8000` to the web container at runtime. The proxy reads it in a route handler; no backend URL is baked into the frontend build. Vercel uses its automatically injected `API_SERVICE_URL` binding instead.
5. Run `alembic upgrade head` as a single release job before starting replicated APIs. The provided local Compose startup runs it automatically for its single API container.
6. Put an HTTPS reverse proxy in front of the web service. Set `APP_ORIGIN` to the exact public origin and `SECURE_COOKIES=true`. Keep API, database, and Redis inaccessible from the public network.
7. Create the first administrator using the CLI; verify login, creation/editing of a test lead, notes, reminders, export, recovery, and logout. Delete the test data afterward.

## Security and operational limits

- Authentication fails closed if Redis is unavailable. Configure Redis persistence/availability as needed. IP limiting sees the direct API client address; behind the Next proxy this may be shared. Account limits still apply. Configure trusted proxy handling deliberately before scaling.
- Role enforcement happens on the backend. Admins may delete records and change settings; editors may update CRM; viewers read it. All accounts share one studio.
- Password reset requires SMTP STARTTLS. Provider failures return an error; recovery is never simulated. Rate limiting and generic success wording reduce enumeration, but SMTP timing/error differences should be hardened with an asynchronous mail outbox before public rollout.
- Secrets are environment-only in Phase 1. There is no credential database or frontend secret form. At-rest encryption and key rotation for future stored integration tokens remain Phase 5 work.
- Deletion removes CRM-linked contact data. Audit logs retain action/user/entity identifiers. “Do not contact” is a persistent manual CRM state. Cross-import contact suppression, retention automation, and deletion/suppression reconciliation must be implemented before enabling outreach.
- Requests should also be capped at 1 MB by the reverse proxy; the API header check is not a streaming body limit.
- No quotations, automated AI, live provider integrations, job controls, or outbound messaging are enabled. Do not represent the entire six-phase product as complete.

## Backups and rollback

Back up PostgreSQL daily and before migrations; test restoration into staging. Preserve environment secrets separately. Use a previous image for application rollback only when its schema is compatible. Prefer forward migrations over destructive downgrade. `0001` downgrade deletes all Phase 1 data and is only for disposable environments.

## Health checks

`GET /health` reports API process health, not dependency readiness. Monitor PostgreSQL and Redis separately. Celery can run `app.worker.health`; no business jobs are registered yet. Logs should avoid request bodies, session cookies, reset tokens, or SMTP passwords.
