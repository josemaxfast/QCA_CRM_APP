"""Customer numbers.

Each company has two series:
- "existing": customers that existed when the CRM went live (for example WFC-1001 to WFC-4999)
- "new":      customers added after go-live (for example WFC-5001 and up)

The format and ranges are settings in `number_series`, not code. Numbers are handed out
inside the same transaction that creates the account and the counter row is locked while
that happens, so two people saving at the same moment never get the same number. A number is
never reused.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import Connection

from .db import row

SERIES = ("existing", "new")


def next_customer_number(conn: Connection, entity_id: str, kind: str = "new") -> str:
    if kind not in SERIES:
        raise ValueError(f"unknown series {kind!r}")
    s = row(
        conn,
        "SELECT prefix, next_value, max_value FROM number_series "
        "WHERE entity_id = :e AND kind = :k FOR UPDATE",
        {"e": entity_id, "k": kind},
    )
    if s is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This company has no customer-number format set up yet. Ask an Admin.")
    if s["max_value"] is not None and s["next_value"] > s["max_value"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"The {kind} customer-number range is used up. Ask an Admin to extend it.")
    row(conn, "UPDATE number_series SET next_value = next_value + 1 WHERE entity_id = :e AND kind = :k "
              "RETURNING next_value", {"e": entity_id, "k": kind})
    return f"{s['prefix']}{s['next_value']}"
