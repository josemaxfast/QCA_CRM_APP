"""Settings come from environment variables (or a .env file). Nothing secret is in code."""
from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")

    env: str = "dev"  # dev | test | prod
    # The login the API uses. Every request switches to `app_db_role` before touching data,
    # so row-level security always applies.
    database_url: str = "postgresql+pg8000://postgres:postgres@127.0.0.1:5432/crm"
    # The login used to run database migrations (defaults to the same one).
    migration_database_url: str = ""
    app_db_role: str = "crm_app"

    # Sign-in. "entra" validates Microsoft Entra ID tokens; "dev" trusts an
    # X-Dev-User header and is refused when env=prod.
    auth_mode: str = "dev"
    entra_tenant_id: str = ""
    entra_authority_host: str = "login.microsoftonline.com"
    entra_api_client_id: str = ""
    entra_require_mfa: bool = False

    cors_origins: str = "http://localhost:5174"

    @model_validator(mode="after")
    def _safe(self) -> "Settings":
        if self.env == "prod" and self.auth_mode != "entra":
            raise ValueError("auth_mode must be 'entra' in production")
        if self.auth_mode == "entra" and not (self.entra_tenant_id and self.entra_api_client_id):
            raise ValueError("entra_tenant_id and entra_api_client_id are required for Entra sign-in")
        return self

    @property
    def migration_url(self) -> str:
        return self.migration_database_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
