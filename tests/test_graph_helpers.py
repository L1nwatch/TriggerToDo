import pytest
from fastapi import HTTPException

from app.config import Settings
from app.graph import GraphClient, OPEN_EXTENSION_NAME, build_extension_payload, extract_open_extension


def test_build_extension_payload() -> None:
    payload = build_extension_payload({"pool": "inbox", "wfStatus": "todo", "triggerRef": "rule-1"})

    assert payload["extensionName"] == OPEN_EXTENSION_NAME
    assert payload["pool"] == "inbox"
    assert payload["wfStatus"] == "todo"
    assert payload["triggerRef"] == "rule-1"


def test_extract_open_extension_found() -> None:
    task = {
        "extensions": [
            {"extensionName": "other.ext", "pool": "x"},
            {
                "extensionName": OPEN_EXTENSION_NAME,
                "pool": "work",
                "wfStatus": "active",
                "triggerRef": "abc",
            },
        ]
    }

    fields = extract_open_extension(task)
    assert fields["pool"] == "work"
    assert fields["wfStatus"] == "active"
    assert fields["triggerRef"] == "abc"
    assert "source" in fields
    assert "epicKey" in fields


def test_extract_open_extension_missing() -> None:
    fields = extract_open_extension({"extensions": []})
    assert fields["pool"] is None
    assert fields["wfStatus"] is None
    assert fields["triggerRef"] is None
    assert fields["source"] is None
    assert fields["epicKey"] is None


def test_effective_scopes_filters_reserved() -> None:
    settings = Settings(msal_scopes="Tasks.ReadWrite,offline_access,openid,profile")
    client = GraphClient(db=None, settings=settings)
    assert client._effective_scopes() == ["Tasks.ReadWrite"]


def test_effective_scopes_requires_non_reserved_scope() -> None:
    settings = Settings(msal_scopes="offline_access,openid,profile")
    client = GraphClient(db=None, settings=settings)
    with pytest.raises(HTTPException) as exc:
        client._effective_scopes()
    assert exc.value.status_code == 500


def test_build_auth_url_requires_msal_client_config() -> None:
    settings = Settings(msal_client_id="", msal_client_secret="", msal_scopes="Tasks.ReadWrite")
    client = GraphClient(db=None, settings=settings)
    with pytest.raises(HTTPException) as exc:
        client.build_auth_url(state="abc")
    assert exc.value.status_code == 500
