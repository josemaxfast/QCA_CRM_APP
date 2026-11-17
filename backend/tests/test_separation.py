"""Proof that companies and customer groups can't see each other's records.

These are the tests CLAUDE.md requires:
- a WeFAB user can't read C&J records, including accounts and contacts
- a WeFAB Sales Manager can't read C&J records
- Admins can see both companies
- no one can read another tenant's records
- the app's database role can't bypass row-level security
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.db import Scope, scoped

from .conftest import TENANT_A, TEST_URL


@pytest.fixture(scope="module")
def world(people):
    """One account (with a contact) in each company, made by its own salesperson."""
    out = {}
    for who, name in [("wf1", "WF Customer"), ("cj", "CJ Customer"), ("ot", "Other Group Customer")]:
        r = people[who].post("/api/accounts", json={"name": name})
        assert r.status_code == 201, r.text
        acct = r.json()
        c = people[who].post(f"/api/accounts/{acct['account_id']}/contacts",
                             json={"first_name": "Pat", "last_name": name})
        assert c.status_code == 201, c.text
        out[who] = {"account": acct, "contact": c.json()}
    return out


def _names(resp) -> set[str]:
    assert resp.status_code == 200, resp.text
    return {a["name"] for a in resp.json()}


# --- Company separation ------------------------------------------------------------------

def test_wefab_salesperson_cannot_see_cj_accounts(people, world):
    assert "CJ Customer" not in _names(people["wf1"].get("/api/accounts"))
    cj_id = world["cj"]["account"]["account_id"]
    assert people["wf1"].get(f"/api/accounts/{cj_id}").status_code == 404


def test_wefab_salesperson_cannot_see_cj_contacts(people, world):
    cj_id = world["cj"]["account"]["account_id"]
    assert people["wf1"].get(f"/api/accounts/{cj_id}/contacts").status_code == 404
    contact_id = world["cj"]["contact"]["contact_id"]
    assert people["wf1"].patch(f"/api/contacts/{contact_id}", json={"title": "x"}).status_code == 404


def test_cj_salesperson_cannot_see_wefab_accounts(people, world):
    assert "WF Customer" not in _names(people["cj"].get("/api/accounts"))


def test_wefab_sales_manager_cannot_see_cj(people, world):
    names = _names(people["mgr"].get("/api/accounts"))
    assert "WF Customer" in names and "CJ Customer" not in names
    cj_id = world["cj"]["account"]["account_id"]
    assert people["mgr"].get(f"/api/accounts/{cj_id}").status_code == 404
    assert people["mgr"].patch(f"/api/accounts/{cj_id}", json={"name": "taken"}).status_code == 404


def test_cannot_add_account_to_the_other_company(people):
    r = people["wf1"].post("/api/accounts", json={"name": "Sneaky", "entity_code": "CJ"})
    assert r.status_code == 403


def test_users_list_shows_only_own_company_and_admins(people, world):
    r = people["wf1"].get("/api/users")
    codes = {u["entity_code"] for u in r.json()}
    assert codes == {None, "WF"}


def test_admin_sees_both_companies(people, world):
    names = _names(people["admin"].get("/api/accounts"))
    assert {"WF Customer", "CJ Customer"} <= names
    me = people["admin"].get("/api/me").json()
    assert {e["code"] for e in me["entities"]} == {"WF", "CJ"}


# --- Tenant separation --------------------------------------------------------------------

def test_admin_cannot_see_another_tenant(people, world):
    assert "Other Group Customer" not in _names(people["admin"].get("/api/accounts"))
    ot_id = world["ot"]["account"]["account_id"]
    assert people["admin"].get(f"/api/accounts/{ot_id}").status_code == 404
    assert people["admin"].get(f"/api/accounts/{ot_id}/contacts").status_code == 404


def test_other_tenant_cannot_see_group_a(people, world):
    for who in ("admin_b", "ot"):
        names = _names(people[who].get("/api/accounts"))
        assert names == {"Other Group Customer"}
        assert {e["code"] for e in people[who].get("/api/me").json()["entities"]} == {"OT"}


# --- The database itself enforces it --------------------------------------------------------

def test_raw_sql_is_filtered_by_the_database(world):
    """Even a query with no WHERE clause only returns the caller's company."""
    eng = create_engine(TEST_URL)
    with eng.connect() as c:
        ids = {r[0]: (str(r[1]), r[2]) for r in c.execute(text(
            "SELECT email, user_id, entity_id FROM app_user"))}  # superuser view, for setup only
    eng.dispose()
    uid, eid = ids["sales1.wf@a.test"]
    with scoped(Scope(tenant_id=TENANT_A, level="sales", entity_id=str(eid), user_id=uid)) as conn:
        accounts = conn.execute(text("SELECT name, entity_id, tenant_id FROM account")).all()
        contacts = conn.execute(text("SELECT last_name, entity_id FROM contact")).all()
    assert "WF Customer" in {a[0] for a in accounts}
    assert {str(a[1]) for a in accounts} == {str(eid)} and {str(a[2]) for a in accounts} == {TENANT_A}
    assert {str(c[1]) for c in contacts} == {str(eid)}
    assert "CJ Customer" not in {c[0] for c in contacts}


def test_no_scope_sees_nothing(world):
    """If the API ever forgot to say who is asking, the answer is: nothing."""
    from app.db import get_engine
    from app.config import get_settings

    with get_engine().begin() as conn:
        conn.execute(text(f"SET LOCAL ROLE {get_settings().app_db_role}"))
        for t in ("tenant", "entity", "app_user", "account", "contact", "number_series", "audit_log"):
            assert conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() == 0, t


def test_app_role_cannot_bypass_row_level_security(world):
    eng = create_engine(TEST_URL)
    with eng.connect() as c:
        role = c.execute(text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'crm_app'")).one()
        assert role == (False, False)
        owned = c.execute(text(
            "SELECT count(*) FROM pg_class WHERE relowner = 'crm_app'::regrole")).scalar()
        assert owned == 0, "crm_app must not own any table (owners can skip RLS)"
        unprotected = c.execute(text(
            "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' "
            "AND relname <> 'alembic_version' AND NOT (relrowsecurity AND relforcerowsecurity)")).all()
        assert unprotected == [], f"tables without forced RLS: {unprotected}"
        no_rights = c.execute(text(
            "SELECT has_table_privilege('crm_app', 'alembic_version', 'SELECT')")).scalar()
        assert no_rights is False
    eng.dispose()


def test_sign_in_lookup_is_read_only():
    from sqlalchemy.exc import DBAPIError

    from app.db import sign_in_lookup

    with pytest.raises(DBAPIError):
        with sign_in_lookup() as conn:
            conn.execute(text("UPDATE app_user SET display_name = 'x'"))


def test_unknown_person_is_refused(client):
    r = client.get("/api/me", headers={"X-Dev-User": "stranger@nowhere.test"})
    assert r.status_code == 403
