"""Accounts (customers, prospects, vendors) and their contacts.

Who may do what is enforced by the database (row-level security). The checks here only
turn the database's "no" into a clear message.
"""
from __future__ import annotations

import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from ..auth import CurrentUser, get_current_user
from ..db import row, rows
from ..deps import user_conn
from ..numbering import next_customer_number

router = APIRouter(prefix="/api", tags=["accounts"])

ACCOUNT_COLS = (
    "a.account_id, a.entity_id, e.code AS entity_code, a.customer_number, a.kind, a.intercompany, "
    "a.name, a.dba, a.website, a.industry, a.status, a.bill_to, a.ship_to, a.payment_terms, "
    "a.pricing_tier, a.tax_exempt, a.owner_user_id, u.display_name AS owner_name, a.source, "
    "a.parent_account_id, a.fulcrum_id, a.existed_at_golive, a.confidential, a.last_activity_at, "
    "a.created_at, a.updated_at"
)
ACCOUNT_FROM = "account a JOIN entity e USING (entity_id) LEFT JOIN app_user u ON u.user_id = a.owner_user_id"

JSON_FIELDS = {"bill_to", "ship_to"}


class Address(BaseModel):
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    country: str = "US"


class AccountFields(BaseModel):
    kind: Literal["customer", "prospect", "vendor"] | None = None
    intercompany: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    dba: str | None = None
    website: str | None = None
    industry: str | None = None
    status: Literal["prospect", "active", "inactive"] | None = None
    bill_to: Address | None = None
    ship_to: Address | None = None
    payment_terms: str | None = None
    pricing_tier: str | None = None
    tax_exempt: bool | None = None
    source: str | None = None
    parent_account_id: UUID | None = None
    fulcrum_id: str | None = None
    confidential: bool | None = None


class AccountCreate(AccountFields):
    name: str = Field(min_length=1, max_length=200)
    entity_code: str | None = None  # Admins only: which company
    owner_user_id: UUID | None = None  # defaults to the person creating it


class AccountUpdate(AccountFields):
    owner_user_id: UUID | None = None


def _dump(fields: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in fields.items():
        if k in JSON_FIELDS:
            out[k] = json.dumps(v)
        elif isinstance(v, UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _placeholder(k: str) -> str:
    return f"CAST(:{k} AS jsonb)" if k in JSON_FIELDS else f":{k}"


def get_visible_account(conn: Connection, account_id: UUID) -> dict[str, Any]:
    a = row(conn, f"SELECT {ACCOUNT_COLS} FROM {ACCOUNT_FROM} WHERE a.account_id = :i",
            {"i": str(account_id)})
    if a is None:
        # Same answer whether it doesn't exist or belongs to someone you may not see.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return a


@router.get("/accounts")
def list_accounts(
    q: str = Query(default="", max_length=100),
    owner: UUID | None = None,
    conn: Connection = Depends(user_conn),
):
    where, p = ["true"], {}
    if q:
        where.append("(a.name ILIKE :q OR a.dba ILIKE :q OR a.customer_number ILIKE :q)")
        p["q"] = f"%{q}%"
    if owner:
        where.append("a.owner_user_id = :o")
        p["o"] = str(owner)
    return rows(conn, f"SELECT {ACCOUNT_COLS} FROM {ACCOUNT_FROM} WHERE {' AND '.join(where)} "
                      f"ORDER BY lower(a.name) LIMIT 500", p)


@router.get("/accounts/{account_id}")
def get_account(account_id: UUID, conn: Connection = Depends(user_conn)):
    return get_visible_account(conn, account_id)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountCreate,
    user: CurrentUser = Depends(get_current_user),
    conn: Connection = Depends(user_conn),
):
    if user.is_admin:
        if not body.entity_code:
            raise HTTPException(422, "Pick which company this account belongs to")
        ent = row(conn, "SELECT entity_id FROM entity WHERE code = :c", {"c": body.entity_code})
        if ent is None:
            raise HTTPException(422, f"Unknown company {body.entity_code}")
        entity_id = str(ent["entity_id"])
        if body.owner_user_id is None:
            raise HTTPException(422, "Pick the salesperson who owns this account")
    else:
        entity_id = user.entity_id
        if body.entity_code:
            ent = row(conn, "SELECT entity_id FROM entity WHERE code = :c", {"c": body.entity_code})
            if ent is None or str(ent["entity_id"]) != entity_id:
                raise HTTPException(403, "You can only add accounts to your own company")
    owner = str(body.owner_user_id) if body.owner_user_id else user.user_id
    if user.level == "sales" and owner != user.user_id:
        raise HTTPException(403, "Accounts you add are owned by you. Ask your Sales Manager to reassign it.")
    if body.confidential and not user.manages(entity_id):
        raise HTTPException(403, "Only a Sales Manager or Admin can mark an account Confidential")
    _check_owner(conn, owner, entity_id)

    fields = body.model_dump(exclude_none=True, exclude={"entity_code", "owner_user_id"}, mode="json")
    fields.update(
        tenant_id=user.tenant_id,
        entity_id=entity_id,
        owner_user_id=owner,
        created_by=user.user_id,
        customer_number=next_customer_number(conn, entity_id, "new"),
    )
    fields = _dump(fields)
    cols = list(fields)
    created = row(conn, f"INSERT INTO account ({', '.join(cols)}) VALUES "
                        f"({', '.join(_placeholder(c) for c in cols)}) RETURNING account_id", fields)
    return get_visible_account(conn, created["account_id"])


def _check_owner(conn: Connection, owner_id: str, entity_id: str) -> None:
    o = row(conn, "SELECT entity_id, level, active FROM app_user WHERE user_id = :u", {"u": owner_id})
    if o is None or not o["active"] or str(o["entity_id"]) != entity_id or o["level"] not in ("sales", "manager"):
        raise HTTPException(422, "The owner must be an active salesperson or Sales Manager of this company")


@router.patch("/accounts/{account_id}")
def update_account(
    account_id: UUID,
    body: AccountUpdate,
    user: CurrentUser = Depends(get_current_user),
    conn: Connection = Depends(user_conn),
):
    current = get_visible_account(conn, account_id)
    entity_id = str(current["entity_id"])
    fields = body.model_dump(exclude_unset=True, mode="json")
    if not fields:
        return current
    if "owner_user_id" in fields and fields["owner_user_id"] != str(current["owner_user_id"]):
        if not user.manages(entity_id):
            raise HTTPException(403, "Only a Sales Manager or Admin can reassign an account")
        if fields["owner_user_id"] is None:
            raise HTTPException(422, "An account always has an owner")
        _check_owner(conn, fields["owner_user_id"], entity_id)
    if "confidential" in fields and not user.manages(entity_id):
        raise HTTPException(403, "Only a Sales Manager or Admin can change the Confidential flag")
    for k in ("name", "kind", "status", "intercompany", "tax_exempt", "confidential", "bill_to", "ship_to"):
        if k in fields and fields[k] is None:
            raise HTTPException(422, f"{k} can't be empty")
    # A blank text field becomes ""; a blank parent account means "no parent".
    fields = _dump({k: ("" if v is None and k != "parent_account_id" else v) for k, v in fields.items()})
    sets = ", ".join(f"{k} = {_placeholder(k)}" for k in fields)
    updated = row(conn, f"UPDATE account SET {sets} WHERE account_id = :_id RETURNING account_id",
                  {**fields, "_id": str(account_id)})
    if updated is None:
        raise HTTPException(403, "You can view this account, but only its owner, the Sales Manager "
                                 "or an Admin can change it")
    return get_visible_account(conn, account_id)


# --------------------------------------------------------------------------------------
# Contacts
# --------------------------------------------------------------------------------------
CONTACT_COLS = ("contact_id, account_id, entity_id, first_name, last_name, title, email, phone, role, "
                "preferred_method, do_not_contact, created_at, updated_at")


class ContactFields(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    title: str | None = None
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    role: Literal["buyer", "engineer", "ap", "other"] | None = None
    preferred_method: Literal["email", "phone", "text", "in_person"] | None = None
    do_not_contact: bool | None = None


@router.get("/accounts/{account_id}/contacts")
def list_contacts(account_id: UUID, conn: Connection = Depends(user_conn)):
    get_visible_account(conn, account_id)
    return rows(conn, f"SELECT {CONTACT_COLS} FROM contact WHERE account_id = :a "
                      f"ORDER BY lower(last_name), lower(first_name)", {"a": str(account_id)})


@router.post("/accounts/{account_id}/contacts", status_code=status.HTTP_201_CREATED)
def create_contact(
    account_id: UUID,
    body: ContactFields,
    user: CurrentUser = Depends(get_current_user),
    conn: Connection = Depends(user_conn),
):
    acct = get_visible_account(conn, account_id)
    fields = body.model_dump(exclude_none=True)
    if not (fields.get("first_name", "").strip() or fields.get("last_name", "").strip()):
        raise HTTPException(422, "A contact needs a first or last name")
    fields.update(tenant_id=user.tenant_id, entity_id=str(acct["entity_id"]), account_id=str(account_id))
    cols = list(fields)
    c = row(conn, f"INSERT INTO contact ({', '.join(cols)}) VALUES ({', '.join(':' + k for k in cols)}) "
                  f"RETURNING {CONTACT_COLS}", fields)
    return c


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: UUID, body: ContactFields, conn: Connection = Depends(user_conn)):
    current = row(conn, f"SELECT {CONTACT_COLS} FROM contact WHERE contact_id = :i", {"i": str(contact_id)})
    if current is None:
        raise HTTPException(404, "Contact not found")
    fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not fields:
        return current
    for k in ("role", "preferred_method", "do_not_contact"):
        if k in fields and fields[k] is None:
            raise HTTPException(422, f"{k} can't be empty")
    fields = {k: ("" if v is None else v) for k, v in fields.items()}
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    c = row(conn, f"UPDATE contact SET {sets} WHERE contact_id = :_id RETURNING {CONTACT_COLS}",
            {**fields, "_id": str(contact_id)})
    if c is None:
        raise HTTPException(403, "You can view this contact, but only the account's owner, the Sales "
                                 "Manager or an Admin can change it")
    return c
