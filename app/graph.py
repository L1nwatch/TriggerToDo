import json
from typing import Any

import msal
import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import UserTokenCache
from app.security import decrypt_str, encrypt_str

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
OPEN_EXTENSION_NAME = "com.triggertodo.meta"
RESERVED_SCOPES = {"openid", "profile", "offline_access"}


class GraphClient:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def _effective_scopes(self) -> list[str]:
        # MSAL handles OIDC reserved scopes internally and rejects them when
        # explicitly passed to get_authorization_request_url.
        raw = self.settings.msal_scopes
        scopes = [scope.strip() for scope in raw.split(",") if scope.strip()]
        cleaned = [scope for scope in scopes if scope not in RESERVED_SCOPES]
        if not cleaned:
            raise HTTPException(status_code=500, detail="MSAL_SCOPES must include at least one non-reserved scope")
        return cleaned

    def _msal_app(self, token_cache: msal.SerializableTokenCache | None = None):
        if not self.settings.msal_client_id:
            raise HTTPException(status_code=500, detail="MSAL_CLIENT_ID is not configured")
        if not self.settings.msal_client_secret:
            raise HTTPException(status_code=500, detail="MSAL_CLIENT_SECRET is not configured")
        return msal.ConfidentialClientApplication(
            client_id=self.settings.msal_client_id,
            client_credential=self.settings.msal_client_secret,
            authority=self.settings.msal_authority,
            token_cache=token_cache,
        )

    def build_auth_url(self, state: str) -> str:
        app = self._msal_app()
        return app.get_authorization_request_url(
            scopes=self._effective_scopes(),
            state=state,
            redirect_uri=self.settings.msal_redirect_uri,
            prompt="select_account",
        )

    def exchange_code(self, code: str) -> dict[str, Any]:
        token_cache = msal.SerializableTokenCache()
        app = self._msal_app(token_cache)
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=self._effective_scopes(),
            redirect_uri=self.settings.msal_redirect_uri,
        )
        if "access_token" not in result:
            raise HTTPException(status_code=401, detail=result.get("error_description", "Token exchange failed"))
        account = result.get("id_token_claims", {})
        user_oid = account.get("oid") or account.get("sub")
        if not user_oid:
            raise HTTPException(status_code=401, detail="Missing user id claim")
        self._store_cache(user_oid, token_cache)
        return result

    def _store_cache(self, user_oid: str, token_cache: msal.SerializableTokenCache):
        if not self.settings.token_cache_key:
            raise HTTPException(status_code=500, detail="TOKEN_CACHE_KEY is not configured")
        serialized = token_cache.serialize()
        encrypted = encrypt_str(self.settings.token_cache_key, serialized)

        existing = self.db.query(UserTokenCache).filter(UserTokenCache.user_oid == user_oid).first()
        if existing:
            existing.encrypted_cache_blob = encrypted
        else:
            self.db.add(UserTokenCache(user_oid=user_oid, encrypted_cache_blob=encrypted))
        self.db.commit()

    def _load_cache(self, user_oid: str) -> msal.SerializableTokenCache:
        record = self.db.query(UserTokenCache).filter(UserTokenCache.user_oid == user_oid).first()
        if not record:
            raise HTTPException(status_code=401, detail="No token cache for user")
        if not self.settings.token_cache_key:
            raise HTTPException(status_code=500, detail="TOKEN_CACHE_KEY is not configured")

        token_cache = msal.SerializableTokenCache()
        token_cache.deserialize(decrypt_str(self.settings.token_cache_key, record.encrypted_cache_blob))
        return token_cache

    def acquire_access_token(self, user_oid: str) -> str:
        token_cache = self._load_cache(user_oid)
        app = self._msal_app(token_cache)

        accounts = app.get_accounts()
        account = accounts[0] if accounts else None
        result = app.acquire_token_silent(scopes=self._effective_scopes(), account=account)

        if not result:
            raise HTTPException(status_code=401, detail="User needs to login again")
        if "access_token" not in result:
            raise HTTPException(status_code=401, detail=result.get("error_description", "Unable to get access token"))

        if token_cache.has_state_changed:
            self._store_cache(user_oid, token_cache)

        return result["access_token"]

    def _request(self, user_oid: str, method: str, path: str, **kwargs) -> dict[str, Any]:
        token = self.acquire_access_token(user_oid)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Content-Type", "application/json")

        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = f"{GRAPH_BASE}{path}"

        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)

        if resp.status_code >= 400:
            detail = resp.text
            raise HTTPException(status_code=resp.status_code, detail=detail)

        if resp.status_code == 204 or not resp.text:
            return {}

        return resp.json()

    def me(self, user_oid: str) -> dict[str, Any]:
        return self._request(user_oid, "GET", "/me")

    def list_lists(self, user_oid: str) -> dict[str, Any]:
        return self._request(user_oid, "GET", "/me/todo/lists")

    def create_list(self, user_oid: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(user_oid, "POST", "/me/todo/lists", data=json.dumps(payload))

    def update_list(self, user_oid: str, list_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(user_oid, "PATCH", f"/me/todo/lists/{list_id}", data=json.dumps(payload))

    def delete_list(self, user_oid: str, list_id: str) -> dict[str, Any]:
        return self._request(user_oid, "DELETE", f"/me/todo/lists/{list_id}")

    def list_tasks(self, user_oid: str, list_id: str) -> dict[str, Any]:
        expand = "$expand=extensions"
        return self._request(user_oid, "GET", f"/me/todo/lists/{list_id}/tasks?{expand}")

    def create_task(self, user_oid: str, list_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(user_oid, "POST", f"/me/todo/lists/{list_id}/tasks", data=json.dumps(payload))

    def update_task(self, user_oid: str, list_id: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(user_oid, "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", data=json.dumps(payload))

    def complete_task(self, user_oid: str, list_id: str, task_id: str) -> dict[str, Any]:
        payload = {"status": "completed"}
        return self._request(user_oid, "PATCH", f"/me/todo/lists/{list_id}/tasks/{task_id}", data=json.dumps(payload))

    def delete_task(self, user_oid: str, list_id: str, task_id: str) -> dict[str, Any]:
        return self._request(user_oid, "DELETE", f"/me/todo/lists/{list_id}/tasks/{task_id}")

    def list_delta(self, user_oid: str, delta_link: str | None = None) -> dict[str, Any]:
        if delta_link:
            return self._request(user_oid, "GET", delta_link)
        return self._request(user_oid, "GET", "/me/todo/lists/delta")

    def task_delta(self, user_oid: str, list_id: str, delta_link: str | None = None) -> dict[str, Any]:
        if delta_link:
            return self._request(user_oid, "GET", delta_link)
        return self._request(user_oid, "GET", f"/me/todo/lists/{list_id}/tasks/delta?$expand=extensions")


def extract_open_extension(task_payload: dict[str, Any]) -> dict[str, str | None]:
    extensions = task_payload.get("extensions") or []
    for ext in extensions:
        if ext.get("extensionName") == OPEN_EXTENSION_NAME:
            return {
                "pool": ext.get("pool"),
                "wfStatus": ext.get("wfStatus"),
                "triggerRef": ext.get("triggerRef"),
                "source": ext.get("source"),
                "epicKey": ext.get("epicKey"),
            }
    return {"pool": None, "wfStatus": None, "triggerRef": None, "source": None, "epicKey": None}


def build_extension_payload(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "@odata.type": "microsoft.graph.openTypeExtension",
        "extensionName": OPEN_EXTENSION_NAME,
        "pool": fields.get("pool"),
        "wfStatus": fields.get("wfStatus"),
        "triggerRef": fields.get("triggerRef"),
        "source": fields.get("source"),
        "epicKey": fields.get("epicKey"),
    }
