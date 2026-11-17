"""Database access.

Every request runs inside one transaction that first switches to the restricted `crm_app`
role and then records who is asking (tenant, company, user, level). PostgreSQL row-level
security then hides every row that person may not see, even if a query forgets a filter.
The values are set with `set_config(..., true)`, which lasts only for this transaction, so a
pooled connection never carries one person's access into the next request.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator

from sqlalchemy import Connection, Engine, create_engine, text

from .config import get_settings

_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
LEVELS = ("sales", "manager", "admin", "system")


@dataclass(frozen=True)
class Scope:
    """Who a transaction acts for."""

    tenant_id: str
    level: str  # sales | manager | admin | system
    entity_id: str | None = None
    user_id: str | None = None

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise ValueError(f"unknown level {self.level!r}")
        if self.level in ("sales", "manager") and not self.entity_id:
            raise ValueError("sales and manager scopes need a company")


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def _enter_app_role(conn: Connection) -> None:
    role = get_settings().app_db_role
    if not _ROLE_RE.match(role):
        raise ValueError("invalid app_db_role")
    conn.execute(text(f"SET LOCAL ROLE {role}"))


@contextmanager
def scoped(scope: Scope) -> Iterator[Connection]:
    with get_engine().begin() as conn:
        _enter_app_role(conn)
        conn.execute(
            text(
                "SELECT set_config('app.tenant_id', :t, true), set_config('app.entity_id', :e, true), "
                "set_config('app.user_id', :u, true), set_config('app.level', :l, true)"
            ),
            {"t": scope.tenant_id, "e": scope.entity_id or "", "u": scope.user_id or "", "l": scope.level},
        )
        yield conn


@contextmanager
def sign_in_lookup() -> Iterator[Connection]:
    """A read-only transaction that may look up any user by email or Microsoft id (sign-in)."""
    with get_engine().begin() as conn:
        _enter_app_role(conn)
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SELECT set_config('app.auth_lookup', 'on', true)"))
        yield conn


def rows(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params or {})]


def row(conn: Connection, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    r = conn.execute(text(sql), params or {}).first()
    return dict(r._mapping) if r else None
