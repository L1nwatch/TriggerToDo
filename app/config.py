from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TriggerToDo Backend"
    debug: bool = False
    database_url: str = "sqlite:///./triggertodo.db"

    session_secret_key: str = "dev-secret-change-me"
    session_cookie_name: str = "triggertodo_session"
    frontend_dir: str = "frontend/dist"

    msal_client_id: str = ""
    msal_client_secret: str = ""
    msal_tenant_id: str = "common"
    msal_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    msal_authority: str = "https://login.microsoftonline.com/common"
    msal_scopes: str = "Tasks.ReadWrite"

    token_cache_key: str = ""

    trigger_webhook_secret: str = "replace-this"
    trigger_engine_interval_seconds: int = 30

    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_default_project_key: str = "2026"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
