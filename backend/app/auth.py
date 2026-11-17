"""Sign-in.

Production: the browser signs in with Microsoft Entra ID (MSAL) and sends an access token.
We check its signature against Microsoft's published keys, the tenant and the audience, then
match the person to `app_user` by Microsoft object id (or email on first sign-in). People who
aren't set up are refused: an Admin or Sales Manager adds users.

Development: `auth_mode=dev` trusts an `X-Dev-User: email` header. The settings refuse this
mode when env=prod.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text

from .config import Settings, get_settings
from .db import Scope, row, scoped, sign_in_lookup


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    tenant_id: str
    entity_id: str | None
    level: str  # sales | manager | admin
    email: str
    display_name: str

    @property
    def scope(self) -> Scope:
        return Scope(tenant_id=self.tenant_id, level=self.level, entity_id=self.entity_id,
                     user_id=self.user_id)

    @property
    def is_admin(self) -> bool:
        return self.level == "admin"

    def manages(self, entity_id: str) -> bool:
        return self.is_admin or (self.level == "manager" and self.entity_id == entity_id)


@lru_cache
def _jwks(host: str, tenant: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"https://{host}/{tenant}/discovery/v2.0/keys")


def verify_entra_token(token: str, s: Settings) -> dict[str, Any]:
    try:
        key = _jwks(s.entra_authority_host, s.entra_tenant_id).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=[s.entra_api_client_id, f"api://{s.entra_api_client_id}"],
            issuer=[
                f"https://{s.entra_authority_host}/{s.entra_tenant_id}/v2.0",
                f"https://sts.windows.net/{s.entra_tenant_id}/",
            ],
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid sign-in token: {e}") from None
    if claims.get("tid") and claims["tid"] != s.entra_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token is from another tenant")
    if s.entra_require_mfa and "mfa" not in (claims.get("amr") or []):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Multi-factor sign-in required")
    return claims


def load_user(*, email: str, oid: str | None) -> CurrentUser:
    with sign_in_lookup() as conn:
        u = None
        if oid:
            u = row(conn, "SELECT * FROM app_user WHERE entra_oid = :o", {"o": oid})
        if u is None and email:
            u = row(conn, "SELECT * FROM app_user WHERE lower(email) = lower(:e)", {"e": email})
    if u is None or not u["active"]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"{email or 'This account'} is not set up in the CRM. Ask an Admin or your Sales Manager to add you.",
        )
    user = CurrentUser(
        user_id=str(u["user_id"]),
        tenant_id=str(u["tenant_id"]),
        entity_id=str(u["entity_id"]) if u["entity_id"] else None,
        level=u["level"],
        email=u["email"],
        display_name=u["display_name"],
    )
    if oid and not u["entra_oid"]:
        # First Microsoft sign-in: remember the person's Microsoft id.
        with scoped(Scope(tenant_id=user.tenant_id, level="system", user_id=user.user_id)) as conn:
            conn.execute(text("UPDATE app_user SET entra_oid = :o WHERE user_id = :i AND entra_oid IS NULL"),
                         {"o": oid, "i": user.user_id})
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
    s: Settings = Depends(get_settings),
) -> CurrentUser:
    if s.auth_mode == "dev":
        if not x_dev_user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required (X-Dev-User)")
        return load_user(email=x_dev_user, oid=None)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    claims = verify_entra_token(authorization.split(" ", 1)[1], s)
    email = claims.get("preferred_username") or claims.get("email") or claims.get("upn") or ""
    return load_user(email=email, oid=claims.get("oid"))
