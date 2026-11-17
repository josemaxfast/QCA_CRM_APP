"""Who am I, which companies can I see, and who are my coworkers."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from ..auth import CurrentUser, get_current_user
from ..db import rows
from ..deps import user_conn

router = APIRouter(prefix="/api", tags=["me"])

LEVEL_NAMES = {"sales": "Sales/Estimator", "manager": "Sales Manager", "admin": "Admin"}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user), conn: Connection = Depends(user_conn)):
    entities = rows(conn, "SELECT entity_id, code, name FROM entity ORDER BY code")
    return {
        "user_id": user.user_id,
        "email": user.email,
        "display_name": user.display_name,
        "level": user.level,
        "level_name": LEVEL_NAMES[user.level],
        "entity_id": user.entity_id,
        "entities": entities,
    }


@router.get("/users")
def users(conn: Connection = Depends(user_conn)):
    """People you can see: your own company's users and the top Admins."""
    return rows(conn, "SELECT u.user_id, u.display_name, u.email, u.level, u.entity_id, e.code AS entity_code "
                      "FROM app_user u LEFT JOIN entity e USING (entity_id) "
                      "WHERE u.active ORDER BY e.code NULLS FIRST, u.display_name")
