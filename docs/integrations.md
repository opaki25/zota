# Integration readiness

Only SMTP password recovery is implemented. Other providers are explicitly labeled as not implemented in the application. Reserved environment variables are documented for future work and are not currently read by adapters.

| Provider | Required configuration / approval | Current behavior |
| --- | --- | --- |
| SMTP recovery | Host, port, STARTTLS support, sender, optional username/password | Sends reset links; returns 503 if unavailable |
| Google Places | API project, billing, API key, approved usage/retention | Not implemented |
| Search provider | Approved API and key, documented permitted discovery usage | Not implemented |
| OpenAI | Server-side key, model selection, validated schemas, usage budget | Not implemented |
| TikTok | Registered application, official OAuth redirect, approved scopes | Not implemented; no search or DM assumptions |
| WhatsApp Cloud API | Business account, phone number, token, verified webhook, templates | Not implemented; cannot send |
| Outreach email | Provider account, authenticated sender domain, webhook verification | Not implemented; cannot send |

## SMTP

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `MAIL_FROM` server-side. `APP_ORIGIN` must be the URL a user can open. Test recovery with a real configured mailbox in staging. The application stores only a SHA-256 digest of each reset token and invalidates older tokens when a new reset is created.

## Requirements before adding delivery

Implement durable consent evidence, channel eligibility checks, jurisdiction-specific configuration, sender identity, template approval state, WhatsApp messaging windows, opt-out processing, cross-import suppression, an atomic idempotent outbox, and provider-event deduplication. Every send must reference an approved draft; AI suggestions must never send autonomously. Webhook signatures must be verified against raw request bytes before persistence. These are implementation prerequisites, not claims of present behavior.

Provider scope and policy requirements should be checked against official documentation at integration time. Publicly listed contact data is not recipient opt-in. Use manual profile links where official social messaging functionality is unavailable.
