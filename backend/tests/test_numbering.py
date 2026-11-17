"""Customer numbers: WFC-5001+ for new customers, WFC-1001..4999 for existing ones."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.db import Scope, scoped
from app.numbering import next_customer_number

from .conftest import TENANT_A, TEST_URL


def _ids(email):
    eng = create_engine(TEST_URL)
    with eng.connect() as c:
        r = c.execute(text("SELECT user_id, entity_id FROM app_user WHERE email = :e"), {"e": email}).one()
    eng.dispose()
    return str(r[0]), str(r[1]) if r[1] else None


def test_new_accounts_get_new_series_numbers_per_company(people):
    a = people["wf1"].post("/api/accounts", json={"name": "Num A"}).json()["customer_number"]
    b = people["wf2"].post("/api/accounts", json={"name": "Num B"}).json()["customer_number"]
    c = people["cj"].post("/api/accounts", json={"name": "Num C"}).json()["customer_number"]
    assert a.startswith("WFC-5") and b.startswith("WFC-5") and c.startswith("CJC-5")
    assert int(b[4:]) == int(a[4:]) + 1


def test_existing_series_starts_at_1001_and_never_collides():
    uid, eid = _ids("manager.wf@a.test")
    with scoped(Scope(tenant_id=TENANT_A, level="manager", entity_id=eid, user_id=uid)) as conn:
        first = next_customer_number(conn, eid, "existing")
        second = next_customer_number(conn, eid, "existing")
        new = next_customer_number(conn, eid, "new")
    assert first == "WFC-1001" and second == "WFC-1002"
    assert int(new[4:]) >= 5001


def test_range_used_up_is_refused():
    uid, eid = _ids("manager.wf@a.test")
    with pytest.raises(HTTPException) as e:
        with scoped(Scope(tenant_id=TENANT_A, level="manager", entity_id=eid, user_id=uid)) as conn:
            conn.execute(text("UPDATE number_series SET next_value = 5000 WHERE entity_id = :e "
                              "AND kind = 'existing'"), {"e": eid})
            next_customer_number(conn, eid, "existing")
    assert e.value.status_code == 409  # (the transaction rolled back; the counter is unchanged)


def test_salesperson_cannot_change_the_format_or_rewind():
    uid, eid = _ids("sales1.wf@a.test")
    for sql in ("UPDATE number_series SET prefix = 'X-' WHERE kind = 'new'",
                "UPDATE number_series SET next_value = 1 WHERE kind = 'new'"):
        with pytest.raises(DBAPIError):
            with scoped(Scope(tenant_id=TENANT_A, level="sales", entity_id=eid, user_id=uid)) as conn:
                conn.execute(text(sql))


def test_salesperson_cannot_see_other_companys_counters():
    uid, eid = _ids("sales1.wf@a.test")
    with scoped(Scope(tenant_id=TENANT_A, level="sales", entity_id=eid, user_id=uid)) as conn:
        prefixes = {r[0] for r in conn.execute(text("SELECT prefix FROM number_series"))}
    assert prefixes == {"WFC-"}
