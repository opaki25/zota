# Phase 1 schema and API

The initial migration creates normalized `users`, `sessions`, `password_recoveries`, `businesses`, `business_contacts`, `opportunities`, `notes`, `follow_ups`, `audit_logs`, and `preferences`. Foreign keys link contacts, deals, notes, and reminders to businesses. Unique keys cover account email, session/reset token digests, name/country/city, and one opportunity per business. Search/status/date/relationship indexes support the CRM views.

Deletion is explicitly ordered in the API so it works in SQLite and PostgreSQL without reliance on implicit cascades. IDs are UUID strings. Timestamps are stored as naive UTC; follow-up input is normalized from its timezone to UTC. Deal values are fixed-precision USD amounts. International currency conversion is not implemented.

## API

OpenAPI is generated at `/openapi.json`, with interactive documentation at `/docs`. Through the web origin, prefix paths with `/api`.

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/auth/login`, `/auth/logout` | Create/revoke session |
| GET | `/auth/me` | Current role, identity, CSRF token |
| POST | `/auth/recover`, `/auth/reset` | SMTP reset lifecycle |
| GET, POST | `/leads` | List/create businesses |
| PUT, DELETE | `/leads/{id}` | Edit/delete a business and associated CRM data |
| POST | `/leads/import` | Validate and atomically import CSV text |
| GET | `/export` | Download formula-safe CSV |
| GET, POST | `/leads/{id}/notes` | Research notes |
| GET, POST | `/follow-ups` | Internal reminders |
| POST | `/follow-ups/{id}/complete` | Close a reminder |
| GET, PUT | `/settings` | Studio preferences |
| GET | `/audit` | Admin audit records |

All mutation requests require an exact matching `Origin`. Authenticated mutations also require `X-CSRF-Token` from `/auth/me` or successful login. Session cookies are HTTP-only and not returned in JSON. Only token digests are stored.

## Extension plan

Add separate migrations for discovery sources and source records, social profiles, website verification evidence/results, versioned scores, message drafts/approvals, consent events, outbox/delivery events, conversations/messages, quotations, integrations/OAuth state, and background jobs/usage. Do not overload manual Phase 1 statuses with automated delivery truth. Model these separately and derive dashboard counts from actual events.

The list endpoint currently returns all records and uses per-business relationship reads. Add pagination, server-side filtering, and batched relationship queries before using large discovery datasets.
