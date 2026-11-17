"""The three user levels: Sales/Estimator, Sales Manager, Admin."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from .conftest import TEST_URL


@pytest.fixture(scope="module")
def accts(people):
    def make(who, name, **kw):
        r = people[who].post("/api/accounts", json={"name": name, **kw})
        assert r.status_code == 201, r.text
        return r.json()

    return {
        "wf1": make("wf1", "Roles: owned by WF1"),
        "wf2": make("wf2", "Roles: owned by WF2"),
        "cj": make("cj", "Roles: owned by CJ"),
    }


def test_creator_owns_the_account(people, accts):
    assert accts["wf1"]["owner_user_id"] == people["wf1"].user_id
    assert accts["wf1"]["owner_name"] == "Sales WF 1"


def test_salesperson_can_view_but_not_edit_a_coworkers_account(people, accts):
    other = accts["wf2"]["account_id"]
    assert people["wf1"].get(f"/api/accounts/{other}").status_code == 200
    r = people["wf1"].patch(f"/api/accounts/{other}", json={"name": "Mine now"})
    assert r.status_code == 403
    assert people["wf1"].post(f"/api/accounts/{other}/contacts", json={"first_name": "X"}).status_code == 403


def test_salesperson_can_edit_own_account(people, accts):
    mine = accts["wf1"]["account_id"]
    r = people["wf1"].patch(f"/api/accounts/{mine}", json={"website": "example.com"})
    assert r.status_code == 200 and r.json()["website"] == "example.com"
    c = people["wf1"].post(f"/api/accounts/{mine}/contacts", json={"first_name": "Sam", "role": "buyer"})
    assert c.status_code == 201


def test_salesperson_cannot_add_an_account_for_someone_else(people):
    r = people["wf1"].post("/api/accounts", json={"name": "For WF2", "owner_user_id": people["wf2"].user_id})
    assert r.status_code == 403


def test_salesperson_cannot_hand_their_account_to_someone_else(people, accts):
    mine = accts["wf1"]["account_id"]
    r = people["wf1"].patch(f"/api/accounts/{mine}", json={"owner_user_id": people["wf2"].user_id})
    assert r.status_code == 403


def test_manager_can_edit_any_account_in_own_company(people, accts):
    r = people["mgr"].patch(f"/api/accounts/{accts['wf2']['account_id']}", json={"industry": "Aerospace"})
    assert r.status_code == 200 and r.json()["industry"] == "Aerospace"


def test_manager_reassigns_within_own_company_only(people, accts):
    aid = accts["wf1"]["account_id"]
    r = people["mgr"].patch(f"/api/accounts/{aid}", json={"owner_user_id": people["wf2"].user_id})
    assert r.status_code == 200 and r.json()["owner_user_id"] == people["wf2"].user_id
    # Not to a C&J salesperson
    r = people["mgr"].patch(f"/api/accounts/{aid}", json={"owner_user_id": people["cj"].user_id})
    assert r.status_code == 422
    # And not a C&J account at all
    r = people["mgr"].patch(f"/api/accounts/{accts['cj']['account_id']}",
                            json={"owner_user_id": people["wf1"].user_id})
    assert r.status_code == 404
    # Put it back
    r = people["mgr"].patch(f"/api/accounts/{aid}", json={"owner_user_id": people["wf1"].user_id})
    assert r.status_code == 200


def test_admin_can_edit_and_reassign_in_both_companies(people, accts):
    r = people["admin"].patch(f"/api/accounts/{accts['cj']['account_id']}", json={"status": "active"})
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_admin_must_pick_company_and_owner_when_adding(people):
    assert people["admin"].post("/api/accounts", json={"name": "No company"}).status_code == 422
    assert people["admin"].post("/api/accounts", json={"name": "No owner", "entity_code": "CJ"}).status_code == 422
    r = people["admin"].post("/api/accounts", json={"name": "For John", "entity_code": "CJ",
                                                    "owner_user_id": people["cj"].user_id})
    assert r.status_code == 201 and r.json()["entity_code"] == "CJ"


def test_admin_cannot_own_accounts(people):
    r = people["admin"].post("/api/accounts", json={"name": "Admin-owned", "entity_code": "WF",
                                                    "owner_user_id": people["admin"].user_id})
    assert r.status_code == 422


def test_confidential_accounts_hidden_from_salespeople(people):
    r = people["mgr"].post("/api/accounts", json={"name": "Secret Co", "confidential": True,
                                                  "owner_user_id": people["wf1"].user_id})
    assert r.status_code == 201, r.text
    aid = r.json()["account_id"]
    # Even its own owner (a salesperson) can't see it; the manager and Admins can.
    assert people["wf1"].get(f"/api/accounts/{aid}").status_code == 404
    assert people["mgr"].get(f"/api/accounts/{aid}").status_code == 200
    assert people["admin"].get(f"/api/accounts/{aid}").status_code == 200
    assert people["wf1"].post("/api/accounts", json={"name": "x", "confidential": True}).status_code == 403


def test_every_change_is_audited_and_the_log_cannot_be_edited(people, accts):
    aid = accts["wf2"]["account_id"]
    eng = create_engine(TEST_URL)
    with eng.connect() as c:
        log = c.execute(text("SELECT action, user_id FROM audit_log WHERE target_table = 'account' "
                             "AND target_id = :i ORDER BY id"), {"i": aid}).all()
        assert [a for a, _ in log][:1] == ["insert"] and "update" in [a for a, _ in log]
        assert str(log[0][1]) == people["wf2"].user_id
        assert c.execute(text("SELECT has_table_privilege('crm_app', 'audit_log', 'UPDATE'), "
                              "has_table_privilege('crm_app', 'audit_log', 'DELETE')")).one() == (False, False)
    eng.dispose()
