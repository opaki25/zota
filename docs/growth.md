# Discovery and outreach

The campaign targets US businesses without an official website and sells website design as Opaki. Uganda is excluded as a prospect market; it remains the sender location.

## Connect providers

In Vercel Production environment variables, set GOOGLE_PLACES_API_KEY (enable Places API New with billing), BRAVE_SEARCH_API_KEY, and a random CRON_SECRET with at least 32 characters. Provider usage can cost money. Restrict the Google key to Places API. Do not put secrets in NEXT_PUBLIC variables, source control, or research notes.

For the existing Gmail sender set SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USER=opakijonathan30@gmail.com, MAIL_FROM=opakijonathan30@gmail.com and SMTP_PASSWORD to a Google app password. Google requires 2-Step Verification and some account types do not support app passwords. This release does not implement Gmail OAuth.

Redeploy after setting variables. Integrations reports configuration presence, not a successful provider connection. Supply a complete mailing address in Campaign settings; the word Uganda alone is not sufficient. The app appends the address and an unsubscribe link to each email.

## Workflow

Discovery checks up to five Google listings per search. Only operational businesses with explicit US address components and no websiteUri proceed. Brave searches for the business and address. Empty results or any domain outside the conservative directory/social allowlist are excluded as uncertain. Search is evidence, not proof of nonexistence. A reviewer must confirm the identity, check links from the social profiles, provide a contact source URL, and describe their website review. Search-indexed public profiles may be returned; Instagram/TikTok account scraping and DMs are not implemented.

Qualifying saves the business in the CRM. Email addresses are never guessed or fabricated. Drafts are deterministic personalized introductions, not AI claims. Website evidence expires after seven days. Existing websites, non-US leads, stale evidence, recipients who replied/opted out, and unreviewed records are blocked before sending.

An introduction is sent at most once per recipient. A committed recipient claim and atomic message state transition prevent concurrent duplicate sends. A crash or ambiguous SMTP outcome remains Sending or Delivery uncertain and must be checked with the provider; there is no automatic retry. Sent means accepted by SMTP, not delivered/read. Unsubscribe GET displays a confirmation page; its POST suppresses the address without requiring login. Suppressions survive deletion of a business. Do not delete suppression records to resend.

Email replies arrive in Gmail. Record them in Inbox to mark the business Replied or Do not contact. Automatic reply ingestion and follow-ups are not implemented. No repeated follow-ups are sent, so missed reply synchronization does not trigger repeated messages.

## Automation

vercel.json schedules /api/growth/run daily at 14:00 UTC (timing depends on the Vercel plan). CRON_SECRET is forwarded through the web service as Authorization and checked by the API. Both campaign switches default OFF. Automatic email sends at most five one-time introductions per run to already reviewed eligible prospects; it never promotes an unverified discovery result. Redis limits repeated scheduled invocations. Keep preview automation disabled and use a separate preview database.

## WhatsApp and other social channels

WhatsApp marketing templates to US numbers are currently unavailable. The app blocks US WhatsApp sends even with credentials or opt-in. Opaki's number appears in email introductions for inbound inquiries. Instagram and TikTok direct-message integrations are not implemented. The UI reports these limits explicitly.

## Deployment and verification

Apply Alembic revision 0002 before deploying this code. New tables are prospects, outreach, and suppressions. On Supabase they have RLS enabled and no public access policies, because the trusted backend uses direct PostgreSQL access. Existing tables and accounts are preserved.

Run `python -m pytest tests -q` in apps/api and frontend typecheck/build from the repository root. Tests mock external providers and cover exclusion, stale evidence, missing keys, authorization, idempotency, uncertain delivery, and unsubscribe. A real provider smoke test still requires credentials and a consenting test recipient.

Sources:
- https://developers.google.com/maps/documentation/places/web-service/text-search
- https://api-dashboard.search.brave.com/documentation/guides/authentication
- https://support.google.com/accounts/answer/185833
- https://www.twilio.com/docs/api/errors/63049
- https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- https://vercel.com/docs/cron-jobs/manage-cron-jobs
