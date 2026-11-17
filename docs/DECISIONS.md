# Decisions log

## 2026-11-17: Brief v4

**People and access**
- Accounts and contacts belong to one company (entity).
- Three user levels: Sales/Estimator, Sales Manager (Admin rights in their own company), and Admin (both companies).
- Salespeople own the accounts they create, and can view their coworkers' accounts and activity read-only.
- Starting salespeople: WeFAB has Daniel Esqueda and Diego Salazar. C&J has John Toscano.

**Intercompany:** WeFAB and C&J can be each other's vendor or customer, flagged Intercompany, with no commission on that work.

**Numbers:** the CRM owns customer numbers and QCA Quote owns quote numbers. Customers have no numbers today, so the CRM numbers all of them.

**Opportunities:** one opportunity = one RFQ = one bunched quote. A revision restarts the follow-ups.

**Follow-ups:** days 2, 7 and 15, plus a warning 3 days before expiry. Quotes are valid for 21 days, and all timings are calendar days.

**Weekly reconciliation** with QCA Quote. It only produces a report.

**Tax certificates:** California now, with Texas and North Carolina prepared.

## 2026-11-17: Plan approved, with these answers

**Customer numbers:** the format is approved: `WFC-1001`+ for existing customers and `WFC-5001`+ for new ones (`CJC-…` for C&J).

**People**
- Sales Manager for WeFAB: Rider Leon.
- C&J has no Sales Manager for now, so the Admins manage it.
- Admin: Jose Rodriguez.

**Customer upload:** a button on the customer list, with a CSV template. The salesperson column is required.

**Leaderboards:** one per company (visible to that company) and one across the group (Admins only), both in Phase 1.

**Account owners** must be a salesperson or Sales Manager of the account's company. Admins don't own accounts.
