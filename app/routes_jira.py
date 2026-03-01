from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import JiraIssueOverride, TriggerEpic
from app.schemas import JiraIssueUpdate

router = APIRouter(prefix="/api/jira", tags=["jira"])


def _apply_overrides(issues: list[dict], db: Session):
    if not issues:
        return issues
    keys = [str(item.get("key")) for item in issues if item.get("key")]
    if not keys:
        return issues

    rows = (
        db.query(JiraIssueOverride)
        .filter(JiraIssueOverride.issue_key.in_(keys))
        .all()
    )
    overrides = {row.issue_key: row for row in rows}

    patched = []
    for item in issues:
        key = str(item.get("key") or "")
        override = overrides.get(key)
        if override and override.summary:
            out = dict(item)
            out["summary"] = override.summary
            patched.append(out)
        else:
            patched.append(item)
    return patched


@router.get("/health")
def jira_health(request: Request):
    _ = request
    return {"ok": True, "mode": "local-only"}


@router.get("/projects/{project_key}/issues")
def jira_project_issues(
    project_key: str,
    request: Request,
    max_results: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _ = request
    _ = project_key
    rows = (
        db.query(TriggerEpic)
        .order_by(TriggerEpic.updated_at.desc())
        .limit(max_results)
        .all()
    )
    issues = [
        {
            "id": str(row.id),
            "key": row.epic_key,
            "source": "jira",
            "summary": row.name,
            "status": row.status,
            "priority": row.priority,
            "issueType": "Epic",
            "parentKey": None,
        }
        for row in rows
    ]
    issues = _apply_overrides(issues, db)
    return {"project": project_key, "total": len(issues), "count": len(issues), "issues": issues}


@router.get("/projects/{project_key}/epics")
def jira_project_epics(
    project_key: str,
    request: Request,
    max_results: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    _ = request
    _ = project_key
    rows = (
        db.query(TriggerEpic)
        .order_by(TriggerEpic.updated_at.desc())
        .limit(max_results)
        .all()
    )
    issues = [
        {
            "id": str(row.id),
            "key": row.epic_key,
            "source": "jira",
            "summary": row.name,
            "status": row.status,
            "priority": row.priority,
            "issueType": "Epic",
            "parentKey": None,
        }
        for row in rows
    ]
    issues = _apply_overrides(issues, db)
    return {"project": project_key, "total": len(issues), "count": len(issues), "issues": issues}


@router.patch("/issues/{issue_key}")
def jira_update_issue(issue_key: str, payload: JiraIssueUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    fields = payload.model_dump(exclude_none=True)

    row = (
        db.query(JiraIssueOverride)
        .filter(JiraIssueOverride.issue_key == issue_key)
        .first()
    )
    if not row:
        row = JiraIssueOverride(issue_key=issue_key)
        db.add(row)

    if "summary" in fields:
        row.summary = fields.get("summary")

    db.commit()
    return {"ok": True, "issueKey": issue_key, "localOnly": True}
