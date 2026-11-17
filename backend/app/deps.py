"""Request dependencies: who is signed in, and a database connection scoped to them."""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends
from sqlalchemy import Connection

from .auth import CurrentUser, get_current_user
from .db import scoped


def user_conn(user: CurrentUser = Depends(get_current_user)) -> Iterator[Connection]:
    with scoped(user.scope) as conn:
        yield conn
