# QCA CRM: Phase 1 plan (draft for approval)

Prepared 2026-11-17. **No code has been written yet.** This plan follows CLAUDE.md (v4) and copies the patterns already used in QCA Quote (branch `phase1-cost-engine`), so the two apps are built and run the same way.

---

## 1. What Phase 1 delivers, in plain words
Salespeople at WeFAB and C&J can sign in with their Microsoft accounts and work their pipeline:
- Add customers and contacts.
- Log RFQs and calls.
- See their tasks for the day.

When QCA Quote sends a quote, the CRM:
- moves the RFQ along the pipeline
- schedules follow-ups on days 2, 7 and 15
- warns when the quote is about to expire

Each salesperson sees only their own company's records. Sales Managers run their own company. The top Admins see both companies.

## 2. Folder layout

```
qca_crm_app/
├── CLAUDE.md, KICKOFF.md, QUOTE-APP-CHANGES.md
├── docs/
│   ├── PHASE1_PLAN.md       ← this file
│   ├── DECISIONS.md         ← every decision you approve, with the date
│   └── AZURE_COST_ESTIMATE.md   (written before anything is created in Azure)
├── backend/                 ← the server (Python, FastAPI), same style as QCA Quote
│   ├── app/
│   │   ├── auth.py          ← Microsoft sign-in, and who the user is
│   │   ├── db.py            ← every request runs as the restricted database role
│   │   ├── rules/           ← follow-up automation (pure Python, easy to test)
│   │   ├── numbering.py     ← customer numbers
│   │   └── routers/         ← one file per area: accounts, contacts, opportunities,
│   │                          activities, tasks, settings, quote_events, import,
│   │                          reconciliation, api_v1 (for QCA Quote)
│   ├── migrations/          ← database changes, numbered (Alembic)
│   └── tests/               ← separation, roles, rules, events, numbering
├── frontend/                ← the screens (React), same look and navigation as QCA Quote
├── seed/                    ← WeFAB-group setup data (companies, users, defaults). Data, not code.
├── infra/                   ← Azure setup as code (Bicep, the same tool QCA Quote uses)
└── .github/workflows/tests.yml  ← runs every test on every push
```

The **seed/** folder is how we keep the core clean. WeFAB, C&J, the salespeople's names, the stage names and the follow-up days all live there as data. A future customer gets a different seed folder and the same code.

## 3. Database design

### 3a. How the separation works
The setup is the same as QCA Quote, plus a tenant check:
- Each request opens one database transaction and switches to a restricted role, `crm_app`. That role can't skip the separation rules and doesn't own any table.
- The transaction then records who is asking: the tenant, the company (entity), the user's ID, and their level.
- **Row-level security (RLS)** then hides every row that doesn't match, even if a screen or a query forgets a filter. Every table has `FORCE ROW LEVEL SECURITY`.

Two kinds of rule are enforced by the database itself, not just by the screens:

| Rule | Reading | Changing |
|---|---|---|
| Tenant | Only your tenant | Only your tenant |
| Company (entity) | Your company only. Admins see all companies. | Same |
| Ownership | Everyone in the company can **view** | A Sales/Estimator can change only records they own. Sales Managers and Admins can change any record in their scope. |
| Confidential | Admins, and Sales Managers of that company | Same |

The audit log is **append-only**: the app can add entries but never edit or delete them. QCA Quote does the same.

### 3b. The tables

**Setup and people**

| Table | What it holds |
|---|---|
| `tenant` | The customer group (WeFAB group). |
| `entity` | WeFAB, C&J: name, code (`WF`, `CJ`), address. |
| `app_user` | Name, email, Microsoft ID, level (Sales/Estimator, Sales Manager, Admin), company (empty for Admins), active. |

**Customers**

| Table | What it holds |
|---|---|
| `account` | Customer number, kind (customer / prospect / vendor / intercompany), name, DBA, website, industry, status, bill-to, ship-to, payment terms, pricing tier, owner, source, parent account, Fulcrum ID, "existed at go-live" flag, confidential flag, last activity date. |
| `tax_certificate` | Account, state (CA now; TX and NC ready), certificate type (resale, partial manufacturing exemption, other), file, date received, expiry date, review date. |
| `contact` | Account, name, title, email, phone, role (buyer / engineer / AP), preferred contact method, do-not-contact. |

**Sales work**

| Table | What it holds |
|---|---|
| `opportunity` | One RFQ. Account, contact, RFQ number, date received, due date, estimated value, owner, stage, loss reason, and the linked quote: quote number, revision, total, sent date, valid-until date, link, last event sequence. |
| `activity` | Call, email, meeting or note: when, who, linked account, contact or opportunity, short body, confidential flag. |
| `task` | Title, due date, assignee, linked record, status. If the follow-up rules made it: which rule, and which quote and revision. |

**Settings** (one set per company; Admins and that company's Sales Manager can edit)

| Table | What it holds |
|---|---|
| `pipeline_stage` | The stage names and their order. |
| `loss_reason` | The loss reasons. |
| `followup_rule` | The follow-up days (2 / 7 / 15), the expiry warning (3 days before), the RFQ alert (2 days), the re-engage period (90 days), and the certificate alert (30 days). |
| `number_series` | The customer-number format and the next number. |
| `state_tax_rule` | The default review period for certificates in each state (CA, TX, NC). |

**Connection to QCA Quote**

| Table | What it holds |
|---|---|
| `quote_event_inbox` | Every event received from QCA Quote, by event ID: received, processed, ignored as a repeat, ignored as out of date, or waiting for review. This is what stops duplicates. |
| `reconciliation_run`, `reconciliation_finding` | The weekly comparison and what it found. |

**Imports and history**

| Table | What it holds |
|---|---|
| `import_batch`, `import_row` | An uploaded CSV waits here, with suggested matches and duplicate warnings, until someone approves it. Nothing reaches the real tables before then. |
| `audit_log` | Who changed what and when, with before and after values. |

Every table has `tenant_id`. Every business table also has `entity_id`.

## 4. Customer numbers (proposal: please approve or change)
Customers in QCA Quote have no numbers yet, so the CRM creates every number. Quote numbers stay as they are in QCA Quote: `WF-26-0001` style.

| | WeFAB | C&J |
|---|---|---|
| Customers that existed at go-live (imported) | `WFC-1001`, `WFC-1002` … | `CJC-1001` … |
| New customers created after go-live | `WFC-5001`, `WFC-5002` … | `CJC-5001` … |

- The **"C"** (for customer) makes customer numbers easy to tell apart from quote numbers.
- A number starting with **5** means the customer is new since the system went live. The account also stores this as a flag, so reports never rely on reading the number.
- Numbers are never reused, even if an account is deleted.
- Both the format and the starting numbers are settings, so a future customer can use their own.
- Vendors and intercompany accounts use the same series. WeFAB as a vendor to C&J is simply a C&J account with the Intercompany flag.

## 5. Who can do what

| | Sales/Estimator | Sales Manager | Admin |
|---|---|---|---|
| See records | Own company, all salespeople (view only on others') | Own company | Both companies |
| Add accounts, contacts, RFQs | Yes; becomes the owner | Yes | Yes |
| Edit accounts, RFQs, tasks | Only their own | All in own company | All |
| Reassign owners | No | Own company | All |
| See Confidential | No | Own company | All |
| Settings, follow-up rules, users | No | Own company | All |
| Approve imports, the review queue, reconciliation | No | Own company | All |

Starting users (as seed data):
- **WeFAB:** Daniel Esqueda and Diego Salazar, Sales/Estimators.
- **C&J:** John Toscano, Sales/Estimator.
- The Sales Managers and the top Admins are **still needed** (see the questions at the end).

## 6. How QCA Quote and the CRM talk

### 6a. QCA Quote → CRM: quote events
`POST /api/v1/quote-events`, sent by QCA Quote's outbox, one event at a time.

```json
{
  "event_id": "7d1c…",              // unique; a repeat is recognised and ignored
  "type": "quote.sent",             // created | sent | revised | won | lost | expired
  "tenant_id": "…", "entity_code": "WF",
  "crm_opportunity_id": "…",        // set when the quote was started from the CRM
  "customer_number": "WFC-1001",
  "contact_id": "…",
  "quote_number": "WF-26-0042", "revision": 1, "sequence": 3,
  "owner_email": "…",
  "total": 12450.00, "valid_until": "2026-12-08",
  "status": "sent", "loss_reason": null,
  "occurred_at": "2026-11-17T15:04:00Z",
  "quote_url": "https://…/#/quotes/…"
}
```

What the CRM does with each event, in order:
1. **Already seen this event ID?** It answers "OK" and does nothing else. A repeat therefore can never create duplicate tasks.
2. **Out of date?** If the sequence number is lower than the last one already handled for this quote, the event is recorded as "ignored, out of date". Example: a late "sent" arriving after "won".
3. **Can't find the opportunity or customer?** The event goes into a **review queue** for the Sales Manager and Admins. Nothing is guessed.
4. **Otherwise** it updates the opportunity and runs the follow-up rules, all in **one transaction**. Either everything happens or nothing does.

**Who may send events:** only QCA Quote's own Azure identity, holding the app role `Quote.Events.Send` on the CRM. There are no passwords or keys in code.

### 6b. CRM → QCA Quote: customers
`GET /api/v1/customers?entity=WF&q=acme` and `GET /api/v1/customers/{number}` return customers with their contacts. `GET /api/v1/loss-reasons` returns the loss-reason list. QCA Quote reads these with the app role `Customers.Read`.

### 6c. Starting a quote from the CRM
On an RFQ, the **Create quote in QCA Quote** button opens QCA Quote with the customer number, contact and RFQ already filled in.

### 6d. The weekly reconciliation
Once a week, the CRM reads QCA Quote's quote list (read-only) and reports:
- possible duplicate customers
- quotes with no RFQ
- mismatched customer numbers
- status disagreements

The report only flags problems. An Admin or Sales Manager decides what to do.

## 7. Follow-up rules (how they run)
Two kinds of automation:
- **Right away, when an event arrives** (in the same transaction as 6a step 4):
    - Sent: create tasks for day 2, day 7, day 15, and the expiry warning (valid-until minus 3, so day 18).
    - Revised: close the open follow-ups and start again from the revision date.
    - Won: close the tasks, set the RFQ to Won and the account to Active.
    - Lost: close the tasks and record the reason, or create a "pick a loss reason" task.
    - Expired: close the tasks and set the RFQ to Expired.
- **Once a day, a scheduled check:**
    - RFQs with no quote after 2 days: alert for the owner and their Sales Manager.
    - Tax certificates within 30 days of their expiry or review date: alert for the Admins.
    - Accounts with no activity for 90 days go on the re-engage list.
    - The list is ready in Phase 1. Its dashboard comes in Phase 3.

All rules use **calendar days**. The rules are plain Python with their own tests, and their numbers come from the `followup_rule` settings.

## 8. Screens in Phase 1
These copy QCA Quote's dark theme, top navigation, red and gold field warnings, and light/dark toggle.

1. **My day:** my tasks due today and overdue, RFQs waiting on a quote, and quotes expiring this week. Sales Managers see their whole company.
2. **Pipeline:** a card for each RFQ by stage, which you can drag between columns. Filters for company (Admins), salesperson and intercompany. Each column shows its total value.
3. **Account (customer 360):** details, contacts, RFQs and quotes, activity timeline, win rate, quoted vs won, last contact, next task, and tax certificates.
4. **Contact:** details and timeline.
5. **Review queue:** quote events that couldn't be matched.
6. **Import:** upload a CSV, review the matches and duplicates, then approve.
7. **Settings:** stages, loss reasons, follow-up rules, numbering, users.

## 9. Step-by-step build (each step = small commits + tests + a plain-language summary)
| # | Step | Done when |
|---|---|---|
| 1 | Project skeleton: server, screens, test runner, CI | Tests run on GitHub on every push |
| 2 | **Companies, users, levels, row-level security, sign-in** | Separation and role tests pass (see the list in CLAUDE.md) |
| 3 | Accounts, customer numbers, tax certificates, contacts | Numbering tests pass, and the screens work |
| 4 | RFQs, activities, tasks, audit log | Ownership rules proven in tests |
| 5 | Settings (stages, reasons, rules, numbering, users) | A Sales Manager can change only their own company |
| 6 | Quote-event endpoint, inbox, review queue | Duplicate, out-of-order and unmatched tests pass |
| 7 | Follow-up rules and the daily check | Rule tests pass for days 2 / 7 / 15 / 18 and the revision restart |
| 8 | Customer API for QCA Quote | QCA Quote can look up customers (tested with a stand-in) |
| 9 | Import from QCA Quote's customer list, and the CSV import with review | Imported customers get WFC-1xxx and CJC-1xxx numbers |
| 10 | Weekly reconciliation | Report tested against a stand-in QCA Quote |
| 11 | Screens: My day, pipeline, account, contact | Checked in a browser, with screenshots sent to you |
| 12 | Azure setup as code, **not deployed** | Cost estimate written; nothing is created until you approve it |

Steps 1–7 don't depend on QCA Quote at all. Steps 8–10 need the QCA Quote changes in QUOTE-APP-CHANGES.md. Until then, a stand-in plays QCA Quote's part in the tests.

## 10. Azure costs (nothing is created without your approval)
I'll write a full estimate before step 12. The likely cheapest setup is to **share what QCA Quote already uses**:
- **Database:** the same database server, with a separate database for the CRM. That keeps the "separate databases" rule and adds about $0 to the bill.
- **Hosting:** the same Container Apps environment.

The extra pieces would be:
- the CRM's container: roughly $0–10 a month if it sleeps when idle, or $25–50 if always on
- a free Static Web App for the screens
- private file storage for tax certificates: under $1 a month
- a once-a-day scheduled job: pennies

## 11. Questions for you
1. **Customer number format:** OK with `WFC-1001` for existing customers and `WFC-5001`+ for new ones (and `CJC-…` for C&J)?
2. **Sales Managers:** who is the Sales Manager for WeFAB, and who for C&J? Can one person be a manager for one company and a salesperson at the same time?
3. **Top Admins:** who are the ~3 Admins?
4. **WeFAB account owners:** each existing WeFAB customer needs either Daniel or Diego as owner. A two-column list (customer, owner) is enough. All C&J customers go to John.
5. **Leaderboard:** you mentioned healthy internal competition. Should I add a simple leaderboard to Phase 1, by salesperson within each company: quotes sent, won $, and win rate this month? It's small. Otherwise it waits for the Phase 3 dashboards.
