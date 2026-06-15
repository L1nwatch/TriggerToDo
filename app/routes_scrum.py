from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TodoTaskCache, TriggerScrum, TriggerScrumItem
from app.routes_todo import _epic_key_from_raw_json, _source_from_raw_json, _upsert_raw_json_from_row
from app.schemas import TriggerScrumCreate, TriggerScrumItemCreate, TriggerScrumItemStatusUpdate, TriggerScrumUpdate

router = APIRouter(prefix="/api/scrums", tags=["scrums"])

SCRUM_STATUSES = {"draft", "active", "completed"}
ITEM_STATUSES = {"todo", "doing", "done"}


def _clean(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_scrum_status(value: str | None) -> str:
    status = str(value or "draft").strip().lower()
    if status not in SCRUM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid scrum status")
    return status


def _normalize_item_status(value: str | None) -> str:
    status = str(value or "todo").strip().lower()
    if status not in ITEM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid item status")
    return status


def _points(value: int | None) -> int:
    points = int(value or 0)
    if points < 0:
        raise HTTPException(status_code=400, detail="Points cannot be negative")
    return points


def _ensure_task(db: Session, list_id: str, task_id: str) -> TodoTaskCache:
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
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return row


def _ensure_single_active(db: Session, scrum_id: int | None = None) -> None:
    query = db.query(TriggerScrum).filter(TriggerScrum.status == "active")
    if scrum_id is not None:
        query = query.filter(TriggerScrum.id != scrum_id)
    existing = query.first()
    if existing:
        raise HTTPException(status_code=409, detail="Another scrum is already active")


def _task_payload(row: TodoTaskCache | None) -> dict | None:
    if not row:
        return None
    return {
        "list_id": row.graph_list_id,
        "task_id": row.graph_task_id,
        "title": row.title,
        "status": row.status,
        "wf_status": row.wf_status,
        "importance": row.importance,
        "due_datetime": row.due_datetime,
        "trigger_ref": row.trigger_ref,
        "epic_key": _epic_key_from_raw_json(row.raw_json),
        "source": _source_from_raw_json(row.raw_json),
    }


def _serialize(row: TriggerScrum, db: Session) -> dict:
    items = (
        db.query(TriggerScrumItem)
        .filter(TriggerScrumItem.scrum_id == row.id)
        .order_by(TriggerScrumItem.id.asc())
        .all()
    )
    task_refs = [(item.graph_list_id, item.graph_task_id) for item in items]
    tasks_by_ref: dict[tuple[str, str], TodoTaskCache] = {}
    if task_refs:
        tasks = (
            db.query(TodoTaskCache)
            .filter(TodoTaskCache.deleted.is_(False))
            .filter(TodoTaskCache.graph_task_id.in_([task_id for _, task_id in task_refs]))
            .all()
        )
        tasks_by_ref = {(task.graph_list_id, task.graph_task_id): task for task in tasks}

    item_payloads = []
    points_by_status = {"todo": 0, "doing": 0, "done": 0}
    count_by_status = {"todo": 0, "doing": 0, "done": 0}
    for item in items:
        status = _normalize_item_status(item.status)
        points_by_status[status] += item.points
        count_by_status[status] += 1
        task = tasks_by_ref.get((item.graph_list_id, item.graph_task_id))
        item_payloads.append(
            {
                "id": item.id,
                "list_id": item.graph_list_id,
                "task_id": item.graph_task_id,
                "points": item.points,
                "status": status,
                "added_after_start": item.added_after_start,
                "updated_at": item.updated_at,
                "task": _task_payload(task),
            }
        )

    return {
        "id": row.id,
        "name": row.name,
        "goal": row.goal,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "target_points": row.target_points,
        "status": row.status,
        "completed_at": row.completed_at,
        "updated_at": row.updated_at,
        "summary": {
            "items": len(items),
            "points": sum(item.points for item in items),
            "done_points": points_by_status["done"],
            "points_by_status": points_by_status,
            "count_by_status": count_by_status,
            "added_after_start": len([item for item in items if item.added_after_start]),
        },
        "items": item_payloads,
    }


def _replace_items(
    db: Session,
    row: TriggerScrum,
    items: list[TriggerScrumItemCreate],
    *,
    mark_new_after_start: bool | None = None,
) -> None:
    existing_items = {
        (item.graph_list_id, item.graph_task_id): item
        for item in db.query(TriggerScrumItem).filter(TriggerScrumItem.scrum_id == row.id).all()
    }
    incoming_keys: set[tuple[str, str]] = set()

    for payload in items:
        list_id = str(payload.list_id or "").strip()
        task_id = str(payload.task_id or "").strip()
        if not list_id or not task_id:
            raise HTTPException(status_code=400, detail="Scrum items require list_id and task_id")
        _ensure_task(db, list_id, task_id)
        key = (list_id, task_id)
        incoming_keys.add(key)
        item = existing_items.get(key)
        if item:
            item.points = _points(payload.points)
            item.status = _normalize_item_status(payload.status)
            continue
        db.add(
            TriggerScrumItem(
                scrum_id=row.id,
                graph_list_id=list_id,
                graph_task_id=task_id,
                points=_points(payload.points),
                status=_normalize_item_status(payload.status),
                added_after_start=row.status == "active" if mark_new_after_start is None else mark_new_after_start,
            )
        )

    for key, item in existing_items.items():
        if key not in incoming_keys:
            db.delete(item)


def _sync_task_workflow(db: Session, item: TriggerScrumItem, status: str) -> None:
    task = _ensure_task(db, item.graph_list_id, item.graph_task_id)
    task.wf_status = status
    if status == "done":
        task.status = "completed"
    elif str(task.status or "").lower() == "completed":
        task.status = "notStarted"
    _upsert_raw_json_from_row(task)


@router.get("")
def list_scrums(request: Request, db: Session = Depends(get_db)):
    _ = request
    rows = db.query(TriggerScrum).order_by(TriggerScrum.id.desc()).all()
    return {"count": len(rows), "items": [_serialize(row, db) for row in rows]}


@router.get("/active")
def get_active_scrum(request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerScrum).filter(TriggerScrum.status == "active").order_by(TriggerScrum.id.desc()).first()
    if not row:
        return {"item": None}
    return {"item": _serialize(row, db)}


@router.post("")
def create_scrum(payload: TriggerScrumCreate, request: Request, db: Session = Depends(get_db)):
    _ = request
    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Scrum name is required")
    status = _normalize_scrum_status(payload.status)
    if status == "active":
        _ensure_single_active(db)

    row = TriggerScrum(
        name=name,
        goal=_clean(payload.goal),
        start_date=_clean(payload.start_date),
        end_date=_clean(payload.end_date),
        target_points=_points(payload.target_points),
        status=status,
    )
    db.add(row)
    db.flush()
    _replace_items(db, row, payload.items, mark_new_after_start=False)
    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.patch("/{scrum_id}")
def update_scrum(scrum_id: int, payload: TriggerScrumUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerScrum).filter(TriggerScrum.id == scrum_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Scrum not found")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Scrum name is required")
        row.name = name
    if "goal" in data:
        row.goal = _clean(data.get("goal"))
    if "start_date" in data:
        row.start_date = _clean(data.get("start_date"))
    if "end_date" in data:
        row.end_date = _clean(data.get("end_date"))
    if "target_points" in data:
        row.target_points = _points(data.get("target_points"))
    if "status" in data:
        status = _normalize_scrum_status(data.get("status"))
        if status == "active":
            _ensure_single_active(db, scrum_id=row.id)
        row.status = status
        if status == "completed" and row.completed_at is None:
            row.completed_at = datetime.now(timezone.utc)
    if payload.items is not None:
        _replace_items(db, row, payload.items)

    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.post("/{scrum_id}/start")
def start_scrum(scrum_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerScrum).filter(TriggerScrum.id == scrum_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Scrum not found")
    _ensure_single_active(db, scrum_id=row.id)
    row.status = "active"
    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.post("/{scrum_id}/complete")
def complete_scrum(scrum_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerScrum).filter(TriggerScrum.id == scrum_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Scrum not found")
    row.status = "completed"
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.patch("/{scrum_id}/items/{item_id}")
def update_scrum_item(
    scrum_id: int,
    item_id: int,
    payload: TriggerScrumItemStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _ = request
    scrum = db.query(TriggerScrum).filter(TriggerScrum.id == scrum_id).first()
    if not scrum:
        raise HTTPException(status_code=404, detail="Scrum not found")
    item = (
        db.query(TriggerScrumItem)
        .filter(TriggerScrumItem.id == item_id, TriggerScrumItem.scrum_id == scrum_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Scrum item not found")
    item.status = _normalize_item_status(payload.status)
    _sync_task_workflow(db, item, item.status)
    db.commit()
    db.refresh(scrum)
    return _serialize(scrum, db)
