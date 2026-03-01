from typing import Any

import requests

from app.config import get_settings


class JiraClient:
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.jira_base_url.rstrip("/")
        self.auth = (self.settings.jira_email, self.settings.jira_api_token)

    def _ensure_configured(self) -> None:
        if not self.base_url or not self.settings.jira_email or not self.settings.jira_api_token:
            raise RuntimeError("Jira is not configured. Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN.")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self._ensure_configured()
        headers = {"Accept": "application/json"}
        if kwargs.get("json") is not None:
            headers["Content-Type"] = "application/json"
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            auth=self.auth,
            headers=headers,
            timeout=20,
            **kwargs,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Jira API error {response.status_code}: {response.text[:300]}")
        if response.status_code == 204 or not response.text:
            return {}
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/rest/api/3/myself")

    def project_issues(self, project_key: str, max_results: int = 50) -> dict[str, Any]:
        max_results = max(1, min(max_results, 100))
        jql = f'project = "{project_key}" ORDER BY updated DESC'
        return self._search(project_key=project_key, jql=jql, max_results=max_results)

    def project_epics(self, project_key: str, max_results: int = 50) -> dict[str, Any]:
        max_results = max(1, min(max_results, 100))
        jql = f'project = "{project_key}" AND issuetype = Epic ORDER BY updated DESC'
        return self._search(project_key=project_key, jql=jql, max_results=max_results)

    def _search(self, project_key: str, jql: str, max_results: int) -> dict[str, Any]:
        payload = self._request(
            "GET",
            "/rest/api/3/search/jql",
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,priority,issuetype,parent",
            },
        )

        issues = []
        for item in payload.get("issues", []):
            fields = item.get("fields") or {}
            issues.append(
                {
                    "id": item.get("id"),
                    "key": item.get("key"),
                    "source": "jira",
                    "summary": fields.get("summary"),
                    "status": (fields.get("status") or {}).get("name"),
                    "priority": (fields.get("priority") or {}).get("name"),
                    "issueType": (fields.get("issuetype") or {}).get("name"),
                    "parentKey": (fields.get("parent") or {}).get("key"),
                }
            )

        return {
            "project": project_key,
            "total": payload.get("total") if isinstance(payload.get("total"), int) and payload.get("total", 0) > 0 else len(issues),
            "count": len(issues),
            "issues": issues,
        }

    def update_issue(self, issue_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        if not fields:
            return {"ok": True}
        self._request(
            "PUT",
            f"/rest/api/3/issue/{issue_key}",
            json={"fields": fields},
        )
        return {"ok": True, "issueKey": issue_key}
