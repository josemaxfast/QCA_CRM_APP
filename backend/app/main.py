"""The CRM API."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from .config import get_settings
from .routers import accounts, me

app = FastAPI(title="QCA CRM", version="0.1.0")

_s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _s.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(me.router)
app.include_router(accounts.router)


def _sqlstate(e: DBAPIError) -> str:
    args = getattr(e.orig, "args", ())
    if args and isinstance(args[0], dict):
        return str(args[0].get("C", ""))
    return str(getattr(e.orig, "sqlstate", "") or "")


@app.exception_handler(DBAPIError)
def database_refused(_: Request, e: DBAPIError):
    """Turn the database's own refusals into clear answers instead of a server error."""
    code = _sqlstate(e)
    if code == "42501":  # row-level security or a permission check said no
        return JSONResponse({"detail": "You don't have permission to make that change"}, status_code=403)
    if code == "23505":
        return JSONResponse({"detail": "That would create a duplicate"}, status_code=409)
    if code in ("23503", "23514", "22P02"):
        return JSONResponse({"detail": "Some of the values aren't valid for this record"}, status_code=422)
    raise e


@app.get("/api/health")
def health():
    return {"ok": True}
