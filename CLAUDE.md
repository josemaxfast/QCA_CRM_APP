# QCA CRM: Project Brief (v3, 2026-11-17)

Read this file fully before planning or writing code. It is the source of truth for this repository.

## What this is
The QCA CRM is the second app in the QCA suite, after **QCA Quote** (already live). It manages customers, contacts, RFQs, follow-ups and the sales pipeline, and connects to QCA Quote so quotes and customer activity live in one place.
- **Owner:** Quality Change Advisors, LLC (QCA). QCA owns all code and IP. Keep the repository under a QCA account.
- **Funding and hosting:** WeFAB pays for this development and hosts it in WeFAB's Azure account. That doesn't change ownership: the code, designs and IP belong to QCA.
- **First users:** Weld Engineering & Fabrication (WeFAB) and C and J Fabrication (C&J). They are two companies under the same parent (the WeFAB group).

## Core product vs customer setup
QCA builds a **clean core**: the general CRM features every manufacturer needs, with nothing specific to one customer built into the code. Each later customer gets their own copy of the core, set up and extended to their needs.
- Anything specific to WeFAB or C&J is **settings or data, not code**. That includes company names, pipeline stages, loss reasons, follow-up days, customer-number formats, and extra fields.
- Customer-specific features go in separate, optional modules. They are never edits scattered through the core.
- Each customer gets its **own deployment**: its own Azure resources and its own database. Infrastructure is written as code (Bicep or Terraform), so the same setup can be redeployed for a new customer in their own Azure account.
- Every table still carries `tenant_id`, with row-level security. This is a safety net, and it keeps the option open to host several customers together later.

## Companies (entities) and access (build this first, and never break it)
- **Tenant:** the customer group, for example the WeFAB group. Every table carries `tenant_id`.
- **Entity:** an operating company inside the tenant, for example WeFAB or C&J. **Every business record carries `entity_id`, including accounts and contacts.** Each manufacturer has its own capabilities, so each keeps its own customers. If the same real company buys from both WeFAB and C&J, it is two separate accounts, one in each entity.
- **Every user except top Admins belongs to exactly one entity** and sees only that entity's records.
- **Enforcement:** PostgreSQL row-level security on `tenant_id` and `entity_id`.
    - The app connects to the database as a non-owner role that **cannot bypass RLS**.
    - Use `FORCE ROW LEVEL SECURITY` on every table.
    - Set the tenant, entity and user per transaction (`SET LOCAL`). Never set them per connection, because connections are reused through the pool.
- **Roles (three levels):**
    - **Sales/Estimator:**
        - Owns the accounts they create. The creator is set as the account owner automatically.
        - Can view their entity's accounts, but can edit only the accounts, opportunities and tasks they own.
    - **Sales Manager:**
        - Has Admin capabilities, limited to their own entity.
        - Can view and edit all of their entity's records, reassign account owners, and manage settings, users and follow-up rules for that entity.
    - **Admin (top level):** about 3 people. They have full rights across every entity in the tenant.
- **Ownership changes:** only a Sales Manager or Admin can change an account's owner. Every change is recorded in the audit log.
- **Confidential flag:** an account or note marked Confidential is visible to Admins and to the Sales Managers of that entity only.
- **Internal users only.** There is no customer portal and no public file upload.

## Intercompany work (WeFAB ↔ C&J)
C&J can use WeFAB as a vendor for sub work, and the other way around.
- Each entity can hold an account for its sister company, marked **Intercompany** (account type, or a flag).
- Intercompany opportunities and wins are **excluded from salesperson and commission reporting**. They still appear in pipeline totals, filtered or labelled so they can be separated from outside business.
- Intercompany records follow the same entity rules. A WeFAB salesperson does not see C&J's side of the deal.

## Core records
- **Account:** a customer, prospect, vendor or intercompany account. Fields:
    - Customer number (see "Customer and quote numbers")
    - Company name, DBA, website, industry, status (prospect / active / inactive)
    - Bill-to and ship-to addresses
    - Payment terms and pricing tier
    - Tax-exempt flag, plus the certificate file, issuing state, date received and expiry date (see "Tax-exempt certificates")
    - Owner (salesperson), source, parent account, intercompany flag
    - The Fulcrum customer ID, used for matching
- **Contact:** name, title, email, phone, role (buyer, engineer, AP), preferred contact method, and do-not-contact flag. Each contact belongs to one account, so it carries that account's entity.
- **Opportunity / RFQ:** one opportunity is **one RFQ, and holds one bunched quote**. Customers usually send all the parts for an RFQ in one email, so they go on one quote. Revisions keep the same quote and add a revision number.
    - Account, contact, RFQ number, date received, due date, estimated value, entity, and owner.
    - Stage: New RFQ → Quoting → Quote sent → Follow-up → Won / Lost / No bid / Expired.
    - Loss reason, from a list: price, lead time, capability, no response, other. Admins can edit the list, and the CRM is the master for it.
    - The linked QCA Quote number and its current revision.
- **Activity:** call, email, meeting or note, with a timestamp, the user, the linked records, and a short body.
- **Task:** title, due date, assignee, the record it's linked to, and status. Tasks can be created by the automatic follow-up rules.
- **Audit log:** who changed what and when, on every record. The audit log is protected by the same tenant and entity rules.

## Customer and quote numbers
Each app owns one kind of number, so the two never clash:
- **The CRM owns customer (account) numbers and contacts.** It is the master customer list from day one.
- **QCA Quote owns quote numbers.** It sends each quote number back to the CRM in its quote events.

Numbering rules:
- **At launch,** the CRM imports QCA Quote's existing customers and **keeps their existing customer numbers**, in the same format. Matching uses name and Fulcrum ID, and an Admin reviews the matches before anything is saved.
- **After launch,** new customers created in the CRM get numbers in a **new format** that can never collide with an old one. That makes "new since the system went live" customers easy to spot. The format is a setting (prefix + sequence, per entity). The exact format is an open decision.
- Customer numbers are unique within an entity.
- QCA Quote reads customers and contacts from the CRM API. It stores the CRM customer number on its side, so both apps refer to the same customer the same way.

## Connection to QCA Quote
- **Separate apps.** Each app has its own database and talks to the other over a versioned REST API (`/api/v1`). They do not share a database, so each module can be sold on its own.
- **Service-to-service auth:** Entra ID app roles or a managed identity. No shared passwords or keys in code.
- **Starting a quote from the CRM:** on an opportunity, a "Create quote in QCA Quote" action opens QCA Quote with the customer, contact and CRM opportunity ID already filled in. That is how each quote is tied to its RFQ.
- **Quote → CRM events:** QCA Quote sends events for quote created, sent, revised, won, lost and expired. Each event carries:
    - Event ID, tenant, entity, CRM opportunity ID, CRM customer number, and contact
    - Quote number and revision number
    - Salesperson/owner, total, valid-until date, and status
    - The time it happened, a per-quote sequence number, and the link back to the quote
    - The loss reason, on quote.lost
- **Event handling in the CRM:**
    - Store every received event ID, and process each one only once, so a repeated event never creates duplicates.
    - Use the per-quote sequence number to ignore stale out-of-order events. For example, a late "sent" event that arrives after "won" is ignored.
    - An event that can't be matched to an opportunity or customer goes to an Admin review queue. It is never silently dropped or guessed.
- **CRM → Quote:** QCA Quote reads customers, contacts and the loss-reason list through the CRM API.
- **Weekly reconciliation:** once a week (an Admin can change how often), the CRM compares its customers and opportunities with QCA Quote's. It produces a report for Admins of:
    - possible duplicate customers
    - customer numbers that don't match between the two apps
    - quotes with no matching opportunity
    - opportunities whose quote status disagrees with QCA Quote

  The report only flags. Nothing is merged or changed automatically, and an Admin decides.
- **Deep links:** from a CRM opportunity, "Open in QCA Quote" opens the quote. From a quote, "Open in CRM" opens the account.
- **Required quote-app changes** are in `QUOTE-APP-CHANGES.md`. Do them in the QCA Quote repository, not here.

## Follow-up automation (default rules, editable by an Admin)
All timings are **calendar days**, including weekends, so they can run fully automatically.
- Quotes are valid for **21 days** by default.
- When a quote is **Sent**:
    - Create follow-up tasks for the owner on **day 2, day 7 and day 15**.
    - Create a "quote expires in 3 days" task 3 days before the quote's valid-until date. With the 21-day default, that's day 18.
- When a quote is **Revised**, close the open follow-up tasks for that quote and **restart the countdown** from the revision's sent date.
- When a quote is **Won**, close the open tasks, set the opportunity to Won, and set the account to Active.
- When a quote is **Lost**, close the open tasks.
    - The loss reason is required.
    - If the event arrives without a reason, create a task for the owner to pick one in the CRM.
    - The opportunity stays flagged until a reason is set.
- When a quote **Expires**, set the opportunity to Expired and close the open tasks.
- An RFQ with no quote 2 calendar days after it was received gets an alert on its owner's dashboard, and on their Sales Manager's dashboard.
- An account with no activity for 90 days goes on a re-engage list.
- A tax-exempt certificate expiring within 30 days creates an alert for an Admin.

## Tax-exempt certificates
Rules differ by state. Some resale or exemption certificates never expire, others must be renewed every year or every few years. The app doesn't hard-code a rule:
- Store the certificate file, issuing state, date received, and expiry date.
- If the certificate has no expiry date, set a **review date one year after it was received** (an Admin can change the default). The 30-day alert uses the expiry date or the review date.
- The certificate file is sensitive. Store it in private storage, visible to Admins and the account's own entity only.

## Microsoft 365 integration (Phase 2)
- **Outlook email:** log emails to an account or opportunity with one click, through Microsoft Graph.
    - Each user consents to this for their own mailbox. Never read whole mailboxes in the background.
    - Store the subject, date, sender, recipients and a short snippet, plus a link to the message. Don't store the full body unless the user chooses to.
- **Calendar:** create follow-up meetings and log past meetings as activities.
- **Quotes:** send quote emails from the CRM through Graph, from the user's own mailbox.

## Screens
1. **My day:** tasks due, follow-ups overdue, RFQs waiting on a quote, and quotes expiring this week.
2. **Pipeline board:** cards by stage, dragged between columns, with a filter by entity, owner and intercompany. Each column shows its total value.
3. **Account page (customer 360):**
    - Contacts, opportunities and quotes (pulled from QCA Quote).
    - A timeline of all activity.
    - Win rate, total quoted vs won, last contact and next task.
4. **Contact page:** details plus that contact's activity timeline.
5. **Dashboards (Admin):**
    - Pipeline by stage and age.
    - Win rate and loss reasons by customer, salesperson and entity. Intercompany work is excluded from salesperson figures.
    - Average quote turnaround.
    - Top accounts.
    - The re-engage list.
    - The weekly reconciliation report.
    - Sales Managers see these dashboards for their own entity, and Admins see them for every entity.
6. **Import:** CSV import of accounts and contacts, with a duplicate check and Admin review before anything is saved. Sales-history import from Fulcrum comes in Phase 3.
7. **Settings** (Admins, and Sales Managers for their own entity): pipeline stages, loss reasons, follow-up rules, customer-number format, users and roles.

## QCA's own use (Phase 4)
QCA will run its own separate CRM deployment, not inside WeFAB's Azure, to sell the suite to other manufacturers:
- Prospects with a manufacturing profile: processes, machines, headcount, current quoting tool.
- A demo and trial pipeline.
- **Rule:** never use one customer's data to inform another customer. Market insights come only from QCA's own sales conversations, in aggregate.

## Technical direction (match QCA Quote)
- **Stack:** Python (FastAPI); PostgreSQL (Azure Database for PostgreSQL); React frontend; Entra ID sign-in with MFA through MSAL.
- **Hosting:**
    - Azure Container Apps in WeFAB's Azure account for the first customer, US region only.
    - Infrastructure written as code (Bicep or Terraform), so it can be redeployed for other customers.
    - Separate dev and prod environments.
- **Data protection:** daily backups kept for 30 days, an audit log on every change, HTTPS only, and encryption at rest.
- **Licensing:** no GPL, AGPL, LGPL or other copyleft code. QCA licenses this commercially. Check the license of every new dependency.
- **Look and feel:** match QCA Quote's layout, navigation and dark theme, so the two read as one suite.
- **Field warnings:** a red tint on a required field that's missing, and gold on fields that need review. Clicking a warning jumps to its field.
- **Tests:**
    - Entity and tenant separation:
        - A WeFAB user can't read C&J records, including accounts and contacts.
        - A WeFAB Sales Manager can't read C&J records.
        - Admins can see both companies.
        - No one can read another tenant's records.
        - The app's database role can't bypass RLS.
    - Roles:
        - A Sales/Estimator can't edit another salesperson's account.
        - A Sales Manager can reassign ownership within their own entity only.
    - The follow-up rules (days 2 / 7 / 15, and the expiry warning), including the restart on revision.
    - Quote-event handling, including duplicate, out-of-order and unmatched events.
    - Customer-number rules: imported customers keep their numbers, and new ones use the new format without collisions.

## Phases
1. **MVP:**
    - Entities, tenancy and access control.
    - Accounts (including intercompany and tax certificates), contacts, opportunities, activities and tasks.
    - Customer import from QCA Quote with the existing numbers, and the CRM customer API.
    - Quote events in from QCA Quote, with follow-up automation.
    - The My day, pipeline board and account pages.
    - CSV import of accounts and contacts.
    - The weekly reconciliation report.
2. **Microsoft 365:** Outlook email logging, calendar, and sending quotes from the user's mailbox.
3. **Dashboards and Fulcrum:** the Admin dashboards, Fulcrum sales-history import, and the re-engage list.
4. **QCA's own deployment:** QCA's prospecting pipeline.

Phase 1 depends on the QCA Quote changes in `QUOTE-APP-CHANGES.md`, especially the events and the customer API connection. Plan the two together.

## Decided (2026-11-17)
- Accounts and contacts belong to one entity. A salesperson works for one entity only.
- WeFAB and C&J can be each other's vendor or customer (intercompany), with no commission on that work.
- The CRM is the master for customers and contacts from day one. QCA Quote is the master for quote numbers.
- One opportunity = one RFQ = one bunched quote. A revision restarts the follow-up countdown.
- All follow-up timings are calendar days.
- The loss reason is required in the CRM.
- Three user levels: Sales/Estimator (owns the accounts they enter), Sales Manager (Admin rights within their own entity), and Admin (all entities).
- Follow-ups on days 2, 7 and 15 after a quote is sent. Quotes expire after 21 days.
- The CRM and QCA Quote are reconciled weekly, and the reconciliation only produces a report.

## Open decisions (ask before building the affected feature)
- What is QCA Quote's current customer-number format, and what format should new CRM customers use?
- Who owns each existing account at launch (a salesperson for each one)?
- Can a Sales/Estimator view other salespeople's accounts in the same entity (read-only), or only their own? The current default is read-only, which helps avoid duplicate accounts.
- In which states do customers hold tax-exempt certificates? This affects the default review period.
