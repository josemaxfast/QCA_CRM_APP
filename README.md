# QCA CRM

The customer and sales-pipeline app in the QCA suite. Read `CLAUDE.md` (the project brief) and
`docs/PHASE1_PLAN.md` (the build plan) first.

## What's in here
| Folder | What it is |
|---|---|
| `backend/` | The server (Python, FastAPI) and the database setup (`migrations/`) |
| `frontend/` | The screens (React), with the same look as QCA Quote |
| `seed/` | Setup data for each customer group: companies, number formats, users |
| `docs/` | The plan, the decisions log, and screenshots |

## Run it on a computer (developers)
You need Python 3.11+, Node 22 and PostgreSQL 16.

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
export CRM_DATABASE_URL=postgresql+pg8000://postgres:postgres@127.0.0.1:5432/crm
alembic upgrade head
python -m app.seed ../seed/dev/setup.json      # sample users: admin@dev.test, rider@dev.test, daniel@dev.test …
uvicorn app.main:app --port 8001
```

In a second window:

```bash
cd frontend
npm ci
npm run dev        # opens on http://localhost:5174
```

Sign in by typing one of the sample emails. Microsoft sign-in is used instead once the Entra
settings are filled in (see `frontend/.env.example` and `backend/app/config.py`).

## Tests
```bash
cd backend && pytest -q
```
They create a fresh test database each time (`CRM_TEST_ADMIN_URL` points to a PostgreSQL
login that can create databases). GitHub runs them on every push.
