"""Backend tests run against a real PostgreSQL database, created fresh for each test run.

Set CRM_TEST_ADMIN_URL to a login that can create databases. The default is a local server.

The test world has two customer groups (tenants):
- "Group A" with two companies, WF and CJ, shaped like the WeFAB group
- "Group B" with one company, OT, standing in for some other customer
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ADMIN_URL = os.environ.get("CRM_TEST_ADMIN_URL", "postgresql+pg8000://postgres:postgres@127.0.0.1:5432/postgres")
TEST_DB = "crm_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"

os.environ["CRM_DATABASE_URL"] = TEST_URL
os.environ["CRM_ENV"] = "test"
os.environ["CRM_AUTH_MODE"] = "dev"

BACKEND = Path(__file__).resolve().parents[1]

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"


def _series(prefix: str) -> dict:
    return {"existing": {"prefix": prefix, "start": 1001, "end": 4999},
            "new": {"prefix": prefix, "start": 5001}}


GROUP_A = {
    "tenant_id": TENANT_A,
    "tenant": "Group A",
    "entities": [
        {"code": "WF", "name": "WeFAB (test)", "customer_numbers": _series("WFC-")},
        {"code": "CJ", "name": "C&J (test)", "customer_numbers": _series("CJC-")},
    ],
    "users": [
        {"name": "Admin A", "level": "admin", "entity": None, "email": "admin@a.test"},
        {"name": "Manager WF", "level": "manager", "entity": "WF", "email": "manager.wf@a.test"},
        {"name": "Sales WF 1", "level": "sales", "entity": "WF", "email": "sales1.wf@a.test"},
        {"name": "Sales WF 2", "level": "sales", "entity": "WF", "email": "sales2.wf@a.test"},
        {"name": "Sales CJ", "level": "sales", "entity": "CJ", "email": "sales.cj@a.test"},
    ],
}
GROUP_B = {
    "tenant_id": TENANT_B,
    "tenant": "Group B",
    "entities": [{"code": "OT", "name": "Other Co (test)", "customer_numbers": _series("OTC-")}],
    "users": [
        {"name": "Admin B", "level": "admin", "entity": None, "email": "admin@b.test"},
        {"name": "Sales OT", "level": "sales", "entity": "OT", "email": "sales.ot@b.test"},
    ],
}


@pytest.fixture(scope="session", autouse=True)
def database():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True,
                   env={**os.environ})
    from app.seed import seed

    seed(GROUP_A, TEST_URL)
    seed(GROUP_B, TEST_URL)
    yield
    from app.db import get_engine

    get_engine().dispose()


@pytest.fixture(scope="session")
def client(database):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=True)


class As:
    """Make requests as a given user."""

    def __init__(self, client, email: str):
        self.c, self.h = client, {"X-Dev-User": email}

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self.h, **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self.h, **kw)


@pytest.fixture(scope="session")
def people(client):
    names = {
        "admin": "admin@a.test", "mgr": "manager.wf@a.test", "wf1": "sales1.wf@a.test",
        "wf2": "sales2.wf@a.test", "cj": "sales.cj@a.test", "admin_b": "admin@b.test",
        "ot": "sales.ot@b.test",
    }
    out = {k: As(client, v) for k, v in names.items()}
    for k, a in out.items():
        me = a.get("/api/me").json()
        a.user_id, a.entity_id = me["user_id"], me["entity_id"]
    return out
