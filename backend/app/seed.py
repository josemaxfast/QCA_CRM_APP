"""Set up a customer group (tenant) from a seed file: companies, number formats and users.

Usage:  python -m app.seed ../seed/wefab_group/setup.json

Everything specific to one customer lives in the seed file, not in code. Running it twice
does no harm: things that already exist are left as they are. Users without an email
address are skipped with a warning (they can't sign in without one).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from .config import get_settings
from .db import Scope

def _setup(conn, scope: Scope) -> None:
    conn.execute(text(
        "SELECT set_config('app.tenant_id', :t, true), set_config('app.entity_id', '', true), "
        "set_config('app.user_id', '', true), set_config('app.level', 'system', true)"),
        {"t": scope.tenant_id})


def seed(data: dict[str, Any], database_url: str | None = None) -> str:
    """Create or update the tenant described by `data`. Returns the tenant id."""
    s = get_settings()
    eng = create_engine(database_url or s.migration_url)
    warnings: list[str] = []
    try:
        with eng.begin() as conn:
            conn.execute(text(f"SET LOCAL ROLE {s.app_db_role}"))
            # The seed file carries a fixed tenant id, so running it again finds the same tenant.
            tid = str(data["tenant_id"])
            _setup(conn, Scope(tenant_id=tid, level="system"))
            if conn.execute(text("SELECT 1 FROM tenant WHERE tenant_id = :t"), {"t": tid}).scalar() is None:
                conn.execute(text("INSERT INTO tenant (tenant_id, name) VALUES (:t, :n)"),
                             {"t": tid, "n": data["tenant"]})

            codes: dict[str, str] = {}
            for e in data["entities"]:
                eid = conn.execute(text("SELECT entity_id FROM entity WHERE code = :c"), {"c": e["code"]}).scalar()
                if eid is None:
                    eid = conn.execute(
                        text("INSERT INTO entity (tenant_id, code, name, address) VALUES (:t, :c, :n, :a) "
                             "RETURNING entity_id"),
                        {"t": tid, "c": e["code"], "n": e["name"], "a": e.get("address", "")},
                    ).scalar()
                codes[e["code"]] = str(eid)
                for kind, ser in e.get("customer_numbers", {}).items():
                    conn.execute(
                        text("INSERT INTO number_series (tenant_id, entity_id, kind, prefix, next_value, max_value) "
                             "VALUES (:t, :e, :k, :p, :n, :m) ON CONFLICT (entity_id, kind) DO NOTHING"),
                        {"t": tid, "e": eid, "k": kind, "p": ser["prefix"], "n": ser["start"],
                         "m": ser.get("end")},
                    )

            for u in data.get("users", []):
                email = (u.get("email") or "").strip()
                if not email:
                    warnings.append(f"{u['name']}: no email yet, not added")
                    continue
                exists = conn.execute(text("SELECT 1 FROM app_user WHERE lower(email) = lower(:e)"),
                                      {"e": email}).scalar()
                if exists:
                    continue
                ent = u.get("entity")
                conn.execute(
                    text("INSERT INTO app_user (tenant_id, entity_id, level, email, display_name) "
                         "VALUES (:t, :e, :l, :m, :n)"),
                    {"t": tid, "e": codes[ent] if ent else None, "l": u["level"], "m": email, "n": u["name"]},
                )
    finally:
        eng.dispose()
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return tid


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.seed path/to/setup.json")
    tid = seed(json.loads(Path(sys.argv[1]).read_text()))
    print(f"tenant {tid} ready")


if __name__ == "__main__":
    main()
