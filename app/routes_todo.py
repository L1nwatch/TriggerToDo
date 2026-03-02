import json
from datetime import datetime, timezone
from calendar import monthrange
from datetime import timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.graph import OPEN_EXTENSION_NAME, build_extension_payload
from app.models import TodoListCache, TodoTaskCache
from app.schemas import GraphListCreate, GraphListUpdate, GraphTaskCreate, GraphTaskUpdate

router = APIRouter(prefix="/api/todo", tags=["todo"])

DEFAULT_LIST_ID = "local-list-inbox"
DEFAULT_LIST_NAME = "Inbox"


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _add_months(dt: datetime, months: int) -> datetime:
    total_month = dt.month - 1 + months
    year = dt.year + total_month // 12
    month = total_month % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _next_due_datetime(due_datetime: str | None, recurrence_json: str | None, trigger_ref: str | None) -> str | None:
    due = _parse_iso_datetime(due_datetime)
    now = datetime.now(timezone.utc)
    if not due:
        due = now

    fallback_ref = str(trigger_ref or "").strip().lower()
    if not recurrence_json:
        if fallback_ref == "date:daily":
            return (now + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        if fallback_ref == "date:weekly":
            return (now + timedelta(weeks=1)).isoformat().replace("+00:00", "Z")
        if fallback_ref == "date:monthly":
            return _add_months(now, 1).isoformat().replace("+00:00", "Z")
        if fallback_ref == "date:yearly":
            return _add_months(now, 12).isoformat().replace("+00:00", "Z")
        return None

    try:
        recurrence = json.loads(recurrence_json)
    except json.JSONDecodeError:
        return None

    pattern = recurrence.get("pattern") or {}
    recurrence_type = str(pattern.get("type") or "").lower()
    interval = int(pattern.get("interval") or 1)
    interval = max(interval, 1)

    if recurrence_type == "daily":
        next_due = now + timedelta(days=interval)
    elif recurrence_type in {"weekly", "relativeweekly"}:
        next_due = now + timedelta(weeks=interval)
    elif recurrence_type in {"monthly", "absolutemonthly", "relativemonthly"}:
        next_due = _add_months(now, interval)
    elif recurrence_type in {"yearly", "absoluteyearly", "relativeyearly"}:
        next_due = _add_months(now, 12 * interval)
    elif fallback_ref == "date:yearly":
        next_due = _add_months(now, 12 * interval)
    elif fallback_ref == "date:monthly":
        next_due = _add_months(now, interval)
    elif fallback_ref == "date:weekly":
        next_due = now + timedelta(weeks=interval)
    elif fallback_ref in {"date:daily", "date"}:
        next_due = now + timedelta(days=interval)
    else:
        return None

    return next_due.isoformat().replace("+00:00", "Z")


def _task_payload_from_create(payload: GraphTaskCreate) -> dict[str, Any]:
    body = payload.model_dump(exclude_none=True)
    ext_fields = body.pop("extensions", None)
    if ext_fields and any(ext_fields.get(k) is not None for k in ["pool", "wfStatus", "triggerRef", "source", "epicKey"]):
        body["extensions"] = [build_extension_payload(ext_fields)]
    return body


def _task_payload_from_update(payload: GraphTaskUpdate) -> dict[str, Any]:
    body = payload.model_dump(exclude_unset=True)
    ext_fields = body.pop("extensions", None)
    if ext_fields and any(ext_fields.get(k) is not None for k in ["pool", "wfStatus", "triggerRef", "source", "epicKey"]):
        body["extensions"] = [build_extension_payload(ext_fields)]
    return body


def _source_from_raw_json(raw_json: str | None) -> str:
    if not raw_json:
        return "microsoft-todo"
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return "microsoft-todo"
    for ext in raw.get("extensions") or []:
        if ext.get("extensionName") == OPEN_EXTENSION_NAME and ext.get("source"):
            return str(ext.get("source"))
    return "microsoft-todo"


def _epic_key_from_raw_json(raw_json: str | None) -> str | None:
    if not raw_json:
        return None
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    for ext in raw.get("extensions") or []:
        if ext.get("extensionName") == OPEN_EXTENSION_NAME and ext.get("epicKey"):
            return str(ext.get("epicKey"))
    return None


def _to_task_dict(row: TodoTaskCache) -> dict[str, Any]:
    try:
        raw = json.loads(row.raw_json or "{}")
    except json.JSONDecodeError:
        raw = {}

    source = _source_from_raw_json(row.raw_json)
    extensions = [
        {
            "extensionName": OPEN_EXTENSION_NAME,
            "pool": row.pool,
            "wfStatus": row.wf_status,
            "triggerRef": row.trigger_ref,
            "source": source,
            "epicKey": _epic_key_from_raw_json(row.raw_json),
        }
    ]

    recurrence = None
    if row.recurrence_json:
        try:
            recurrence = json.loads(row.recurrence_json)
        except json.JSONDecodeError:
            recurrence = None

    return {
        "id": row.graph_task_id,
        "title": row.title,
        "status": row.status,
        "importance": row.importance,
        "body": {"contentType": "text", "content": row.body_content or ""},
        "dueDateTime": {"dateTime": row.due_datetime, "timeZone": row.due_timezone or "UTC"}
        if row.due_datetime
        else None,
        "recurrence": recurrence,
        "createdDateTime": raw.get("createdDateTime"),
        "lastModifiedDateTime": raw.get("lastModifiedDateTime"),
        "extensions": extensions,
    }


def _upsert_raw_json_from_row(row: TodoTaskCache):
    now = _utc_iso_now()
    raw: dict[str, Any]
    try:
        raw = json.loads(row.raw_json or "{}")
    except json.JSONDecodeError:
        raw = {}

    created = raw.get("createdDateTime") or now
    ext_source = _source_from_raw_json(row.raw_json)
    ext_epic_key = _epic_key_from_raw_json(row.raw_json)

    raw.update(
        {
            "id": row.graph_task_id,
            "title": row.title,
            "status": row.status,
            "importance": row.importance,
            "body": {"contentType": "text", "content": row.body_content or ""},
            "dueDateTime": {"dateTime": row.due_datetime, "timeZone": row.due_timezone or "UTC"}
            if row.due_datetime
            else None,
            "recurrence": json.loads(row.recurrence_json) if row.recurrence_json else None,
            "createdDateTime": created,
            "lastModifiedDateTime": now,
            "extensions": [
                {
                    "extensionName": OPEN_EXTENSION_NAME,
                    "pool": row.pool,
                    "wfStatus": row.wf_status,
                    "triggerRef": row.trigger_ref,
                    "source": ext_source or "triggertodo",
                    "epicKey": ext_epic_key,
                }
            ],
        }
    )
    row.raw_json = json.dumps(raw)


def _ensure_default_list(db: Session) -> TodoListCache:
    existing = (
        db.query(TodoListCache)
        .filter(TodoListCache.graph_list_id == DEFAULT_LIST_ID)
        .first()
    )
    if existing:
        return existing

    row = TodoListCache(
        graph_list_id=DEFAULT_LIST_ID,
        display_name=DEFAULT_LIST_NAME,
        is_owner=True,
        is_shared=False,
        etag=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/lists")
def list_lists(request: Request, db: Session = Depends(get_db)):
    _ = request
    if db.query(TodoListCache.id).first() is None:
        _ensure_default_list(db)
    rows = db.query(TodoListCache).order_by(TodoListCache.display_name.asc()).all()
    return [{"id": row.graph_list_id, "displayName": row.display_name} for row in rows]


@router.post("/lists")
def create_list(payload: GraphListCreate, request: Request, db: Session = Depends(get_db)):
    _ = request
    list_id = f"local-list-{uuid4().hex}"
    row = TodoListCache(
        graph_list_id=list_id,
        display_name=payload.displayName,
        is_owner=True,
        is_shared=False,
        etag=None,
    )
    db.add(row)
    db.commit()
    return {"id": list_id, "displayName": row.display_name}


@router.patch("/lists/{list_id}")
def update_list(list_id: str, payload: GraphListUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = (
        db.query(TodoListCache)
        .filter(TodoListCache.graph_list_id == list_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="List not found")
    row.display_name = payload.displayName
    db.commit()
    return {"id": row.graph_list_id, "displayName": row.display_name}


@router.delete("/lists/{list_id}")
def delete_list(list_id: str, request: Request, db: Session = Depends(get_db)):
    _ = request
    (
        db.query(TodoTaskCache)
        .filter(TodoTaskCache.graph_list_id == list_id)
        .delete()
    )
    (
        db.query(TodoListCache)
        .filter(TodoListCache.graph_list_id == list_id)
        .delete()
    )
    db.commit()
    return {"ok": True}


@router.get("/lists/{list_id}/tasks")
def list_tasks(list_id: str, request: Request, db: Session = Depends(get_db)):
    _ = request
    rows = (
        db.query(TodoTaskCache)
        .filter(
            TodoTaskCache.graph_list_id == list_id,
            TodoTaskCache.deleted.is_(False),
        )
        .order_by(TodoTaskCache.updated_at.desc())
        .all()
    )
    return {"value": [_to_task_dict(row) for row in rows]}


@router.post("/lists/{list_id}/tasks")
def create_task(list_id: str, payload: GraphTaskCreate, request: Request, db: Session = Depends(get_db)):
    _ = request
    list_row = (
        db.query(TodoListCache)
        .filter(TodoListCache.graph_list_id == list_id)
        .first()
    )
    if not list_row:
        fallback = _ensure_default_list(db)
        list_id = fallback.graph_list_id

    task_id = f"local-task-{uuid4().hex}"

    body = payload.body or {}
    due = payload.dueDateTime or {}
    ext = payload.extensions.model_dump(exclude_none=True)

    source = ext.get("source") or "triggertodo"
    epic_key = ext.get("epicKey")

    row = TodoTaskCache(
        graph_list_id=list_id,
        graph_task_id=task_id,
        title=payload.title,
        body_content=body.get("content"),
        importance=payload.importance or "normal",
        status="notStarted",
        due_datetime=due.get("dateTime"),
        due_timezone=due.get("timeZone") or "UTC",
        recurrence_json=payload.recurrence.model_dump_json() if payload.recurrence else None,
        pool=ext.get("pool"),
        wf_status=ext.get("wfStatus"),
        trigger_ref=ext.get("triggerRef"),
        raw_json=json.dumps(
            {
                "extensions": [
                    {
                        "extensionName": OPEN_EXTENSION_NAME,
                        "pool": ext.get("pool"),
                        "wfStatus": ext.get("wfStatus"),
                        "triggerRef": ext.get("triggerRef"),
                        "source": source,
                        "epicKey": epic_key,
                    }
                ]
            }
        ),
        deleted=False,
    )
    _upsert_raw_json_from_row(row)
    db.add(row)
    db.commit()
    return _to_task_dict(row)


@router.patch("/lists/{list_id}/tasks/{task_id}")
def update_task(list_id: str, task_id: str, payload: GraphTaskUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = (
        db.query(TodoTaskCache)
        .filter(
            TodoTaskCache.graph_list_id == list_id,
            TodoTaskCache.graph_task_id == task_id,
            TodoTaskCache.deleted.is_(False),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    body = payload.model_dump(exclude_unset=True)
    ext_fields = body.pop("extensions", None)

    if "title" in body:
        row.title = str(body["title"])
    if "body" in body:
        row.body_content = (body.get("body") or {}).get("content")
    if "importance" in body:
        row.importance = body.get("importance")
    if "status" in body:
        row.status = body.get("status")
    if "dueDateTime" in body:
        due = body.get("dueDateTime") or {}
        row.due_datetime = due.get("dateTime")
        row.due_timezone = due.get("timeZone") or "UTC"
    if "recurrence" in body:
        recurrence = body.get("recurrence")
        row.recurrence_json = json.dumps(recurrence) if recurrence else None

    if ext_fields:
        if "pool" in ext_fields:
            row.pool = ext_fields.get("pool")
        if "wfStatus" in ext_fields:
            row.wf_status = ext_fields.get("wfStatus")
        if "triggerRef" in ext_fields:
            row.trigger_ref = ext_fields.get("triggerRef")
        if "source" in ext_fields or "epicKey" in ext_fields:
            try:
                raw = json.loads(row.raw_json or "{}")
            except json.JSONDecodeError:
                raw = {}
            extensions = raw.get("extensions") or []
            ext = None
            for item in extensions:
                if item.get("extensionName") == OPEN_EXTENSION_NAME:
                    ext = item
                    break
            if not ext:
                ext = {"extensionName": OPEN_EXTENSION_NAME}
                extensions = [ext]
            if "source" in ext_fields:
                ext["source"] = ext_fields.get("source")
            if "epicKey" in ext_fields:
                ext["epicKey"] = ext_fields.get("epicKey")
            raw["extensions"] = extensions
            row.raw_json = json.dumps(raw)

    _upsert_raw_json_from_row(row)
    db.commit()
    return _to_task_dict(row)


@router.patch("/tasks/{task_id}")
def update_task_by_id(task_id: str, payload: GraphTaskUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    query = (
        db.query(TodoTaskCache)
        .filter(TodoTaskCache.graph_task_id == task_id, TodoTaskCache.deleted.is_(False))
        .order_by(TodoTaskCache.updated_at.desc())
    )
    matches = query.limit(2).all()
    if not matches:
        raise HTTPException(status_code=404, detail="Task not found")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Task ID exists in multiple lists; use list-scoped endpoint")

    row = matches[0]
    return update_task(row.graph_list_id, task_id, payload, request=request, db=db)


@router.post("/lists/{list_id}/tasks/{task_id}/complete")
def complete_task(list_id: str, task_id: str, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = (
        db.query(TodoTaskCache)
        .filter(
            TodoTaskCache.graph_list_id == list_id,
            TodoTaskCache.graph_task_id == task_id,
            TodoTaskCache.deleted.is_(False),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    next_due = _next_due_datetime(row.due_datetime, row.recurrence_json, row.trigger_ref)
    if next_due:
        source = _source_from_raw_json(row.raw_json) or "triggertodo"
        epic_key = _epic_key_from_raw_json(row.raw_json)
        next_row = TodoTaskCache(
            graph_list_id=row.graph_list_id,
            graph_task_id=f"local-task-{uuid4().hex}",
            title=row.title,
            body_content=row.body_content,
            importance=row.importance,
            status="notStarted",
            due_datetime=next_due,
            due_timezone=row.due_timezone or "UTC",
            recurrence_json=row.recurrence_json,
            pool=row.pool,
            wf_status="todo",
            trigger_ref=row.trigger_ref,
            raw_json=json.dumps(
                {
                    "extensions": [
                        {
                            "extensionName": OPEN_EXTENSION_NAME,
                            "pool": row.pool,
                            "wfStatus": "todo",
                            "triggerRef": row.trigger_ref,
                            "source": source,
                            "epicKey": epic_key,
                        }
                    ]
                }
            ),
            deleted=False,
        )
        _upsert_raw_json_from_row(next_row)
        db.add(next_row)

    row.status = "completed"
    _upsert_raw_json_from_row(row)
    db.commit()
    return _to_task_dict(row)


@router.delete("/lists/{list_id}/tasks/{task_id}")
def delete_task(list_id: str, task_id: str, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = (
        db.query(TodoTaskCache)
        .filter(
            TodoTaskCache.graph_list_id == list_id,
            TodoTaskCache.graph_task_id == task_id,
        )
        .first()
    )
    if row:
        row.deleted = True
        _upsert_raw_json_from_row(row)
        db.commit()
    return {"ok": True}


@router.get("/cache/tasks")
def query_cached_tasks(
    request: Request,
    db: Session = Depends(get_db),
    pool: str | None = Query(default=None),
    wf_status: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
):
    _ = request
    query = db.query(TodoTaskCache)
    if not include_deleted:
        query = query.filter(TodoTaskCache.deleted.is_(False))
    if pool is not None:
        query = query.filter(TodoTaskCache.pool == pool)
    if wf_status is not None:
        query = query.filter(TodoTaskCache.wf_status == wf_status)

    rows = query.order_by(TodoTaskCache.updated_at.desc()).all()
    items = []
    for row in rows:
        created_dt = None
        last_modified_dt = None
        if row.raw_json:
            try:
                raw = json.loads(row.raw_json)
                created_dt = raw.get("createdDateTime")
                last_modified_dt = raw.get("lastModifiedDateTime")
            except Exception:
                pass

        items.append(
            {
                "listId": row.graph_list_id,
                "taskId": row.graph_task_id,
                "title": row.title,
                "source": _source_from_raw_json(row.raw_json),
                "status": row.status,
                "importance": row.importance,
                "bodyContent": row.body_content,
                "dueDateTime": row.due_datetime,
                "dueTimeZone": row.due_timezone,
                "recurrenceJson": row.recurrence_json,
                "pool": row.pool,
                "wfStatus": row.wf_status,
                "triggerRef": row.trigger_ref,
                "epicKey": _epic_key_from_raw_json(row.raw_json),
                "createdDateTime": created_dt,
                "lastModifiedDateTime": last_modified_dt,
                "updatedAt": row.updated_at,
                "deleted": row.deleted,
            }
        )

    return {"count": len(rows), "items": items}
