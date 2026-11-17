# First prompt to paste into Claude Code (new qca-crm repository)

Read CLAUDE.md fully. Then do the following:

1. Show me:
    - the repository structure
    - the database schema, with tenant_id and entity_id row-level security
    - the quote-event API
    - the customer API that QCA Quote will read
    - the customer-numbering approach
    - a step-by-step plan for Phase 1

   Wait for my approval before writing code.
2. Build the entity and access layer first. Add tests proving that:
    - a WeFAB user can't see C&J records, including accounts and contacts
    - a Sales/Estimator can edit only the accounts they own
    - a Sales Manager has Admin rights for their own company only
    - top Admins can see both companies
    - no tenant can see another tenant's records
    - the app's database login can't bypass row-level security
3. Then build accounts (including intercompany and tax certificates), contacts, opportunities, activities and tasks. Next, add the customer import from QCA Quote that keeps the existing customer numbers, and the customer API.
4. Then add the quote-event endpoint, with handling for duplicate, out-of-order and unmatched events. After that, add the follow-up rules, including the restart on revision, and the weekly reconciliation report.
5. Then build the My day, pipeline board and account screens. Match the QCA Quote look (dark theme, the same navigation style).

Keep the core clean. Anything specific to WeFAB or C&J goes in settings or data, not in code.

Work in small commits. Explain each step in plain language, because I'm not a developer. Ask before adding paid services or anything that costs money in Azure. If something in CLAUDE.md is unclear or conflicts, ask instead of guessing.
