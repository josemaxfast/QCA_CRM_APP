# Prompt for the QCA Quote repository: get it ready for the CRM

Paste this into Claude Code in the **QCA Quote** repository, not the CRM repository.

```
We're building a separate QCA CRM app that connects to this quote app. Make these changes, explain each step in plain language, and ask before adding anything that costs money in Azure.

Before anything else: show me a plan, and a backup and rollback plan for the database changes. Wait for my approval. This app is live.

1. Add tenant_id to every table, next to entity_id, and enforce both with row-level security. Today there is one tenant (the WeFAB group). The app's database login must not be able to bypass row-level security. Add a test proving that no tenant can see another tenant's data, and that one entity can't see another's.

2. Link quotes to CRM opportunities. One CRM opportunity (one RFQ) holds one quote, and revisions keep the same quote number. Accept a CRM opportunity ID when a quote is started from the CRM (through a link that opens this app with the customer, contact and opportunity filled in), and store it on the quote.

3. Add an outbox table and send these quote events to the CRM: quote.created, quote.sent, quote.revised, quote.won, quote.lost (with the loss reason), and quote.expired.
   Each event carries:
   - event id, tenant_id, entity_id, CRM opportunity id, CRM customer number, contact id
   - quote number, revision number, a per-quote sequence number
   - salesperson/owner, total, valid-until date, status
   - the time it happened, and a link to the quote
   Deliver at least once, with retries. The event id lets the CRM ignore duplicates, and the sequence number lets it ignore out-of-order events.

4. Add a read-only, versioned API (/api/v1) for the CRM:
   - list quotes by CRM customer number
   - get a single quote's summary
   - list all quotes with their customer number and opportunity id, for the CRM's weekly reconciliation
   Protect it with Entra ID app roles (service-to-service), not shared keys.

5. Customers: add a setting, CUSTOMER_SOURCE = local | crm.
   - With local, the app works as it does today.
   - With crm, the customer and contact pickers read from the CRM API.
   - Keep the Fulcrum customer ID on the customer record, and store the CRM customer number (for example WFC-1001). The CRM creates all customer numbers.
   - Provide an export of the existing customer list, with Fulcrum IDs, for the CRM's first import.
   - Quote numbers stay owned by this app.

6. Add an "Open in CRM" link on each quote. It shows only when a CRM URL is configured.

7. Add a "Lost" reason picker. With CUSTOMER_SOURCE = crm, read the reason list from the CRM API. Otherwise use the defaults: price, lead time, capability, no response, other.

Don't change any pricing logic. All existing tests must still pass.
```
