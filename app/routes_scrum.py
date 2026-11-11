from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TodoTaskCache, TriggerScrum, TriggerScrumItem
from app.routes_todo import (
    _apply_task_update,
    _ensure_default_list,
    _epic_key_from_raw_json,
    _find_task_list,
    _new_task,
    _source_from_raw_json,
    _upsert_raw_json_from_row,
)
from app.schemas import (
    GraphTaskCreate,
    GraphTaskUpdate,
    TriggerScrumCreate,
    TriggerScrumItemCreate,
    TriggerScrumItemStatusUpdate,
    TriggerScrumUpdate,
)
from app.scrum_contract import (
    AddScrumItem,
    CreateScrumItem,
    MoveScrumItem,
    RemoveScrumItem,
    ScrumItemBatch,
    ScrumItemBatchResult,
    ScrumItemOperation,
    UpdateScrumItem,
)

router = APIRouter(prefix="/api/scrums", tags=["scrums"])
internal_router = APIRouter(prefix="/internal/scrums", include_in_schema=False)

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


def _check_scrum_dates(start: str | None, end: str | None) -> None:
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Scrum dates must use YYYY-MM-DD") from None
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")


def _lock_scrum_writes(db: Session) -> None:
    if db.get_bind().dialect.name == "sqlite":
        # Reserve the write transaction before reading so a concurrent batch cannot use stale membership.
        db.execute(text("BEGIN IMMEDIATE"))


def _get_scrum_for_write(db: Session, scrum_id: int) -> TriggerScrum:
    row = db.scalar(select(TriggerScrum).where(TriggerScrum.id == scrum_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail=f"Scrum {scrum_id} not found")
    return row


def _get_scrum_item(db: Session, scrum_id: int, item_id: int) -> TriggerScrumItem:
    item = db.get(TriggerScrumItem, item_id)
    if item is None or item.scrum_id != scrum_id:
        raise HTTPException(status_code=404, detail=f"Scrum item {item_id} not found in Scrum {scrum_id}")
    return item


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
        "description": row.body_content,
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
        task = _ensure_task(db, list_id, task_id)
        key = (list_id, task_id)
        if key in incoming_keys:
            raise HTTPException(status_code=409, detail=f"Task {task_id} is listed more than once")
        incoming_keys.add(key)
        item = existing_items.get(key)
        if item:
            item.points = _points(payload.points)
            item.status = _normalize_item_status(payload.status)
            continue
        _new_scrum_item(
            db, row, task, _points(payload.points), _normalize_item_status(payload.status),
            mark_new_after_start=mark_new_after_start,
        )

    for key, item in existing_items.items():
        if key not in incoming_keys:
            db.delete(item)


def _new_scrum_item(
    db: Session,
    scrum: TriggerScrum,
    task: TodoTaskCache,
    points: int,
    status: str,
    *,
    mark_new_after_start: bool | None = None,
) -> TriggerScrumItem:
    item = TriggerScrumItem(
        scrum_id=scrum.id,
        graph_list_id=task.graph_list_id,
        graph_task_id=task.graph_task_id,
        points=points,
        status=status,
        added_after_start=scrum.status == "active" if mark_new_after_start is None else mark_new_after_start,
    )
    db.add(item)
    return item


def _sync_task_workflow(task: TodoTaskCache, status: str) -> None:
    task.wf_status = status
    if status == "done":
        task.status = "completed"
    elif str(task.status or "").lower() == "completed":
        task.status = "notStarted"
    _upsert_raw_json_from_row(task)


def _task_item_status(task: TodoTaskCache) -> str:
    if task.status == "completed" or task.wf_status == "done":
        return "done"
    if task.status == "inProgress" or task.wf_status == "doing":
        return "doing"
    return "todo"


def _ensure_task_not_in_scrum(db: Session, scrum_id: int, list_id: str, task_id: str) -> None:
    item_id = db.scalar(
        select(TriggerScrumItem.id).where(
            TriggerScrumItem.scrum_id == scrum_id,
            TriggerScrumItem.graph_list_id == list_id,
            TriggerScrumItem.graph_task_id == task_id,
        )
    )
    if item_id is not None:
        raise HTTPException(status_code=409, detail=f"Task {task_id} is already in Scrum {scrum_id} as item {item_id}")


def _create_backlog_task(db: Session, operation: CreateScrumItem) -> TodoTaskCache:
    if operation.list_id is None:
        task_list = _ensure_default_list(db)
    else:
        task_list = _find_task_list(db, operation.list_id)
        if task_list is None:
            raise HTTPException(status_code=404, detail=f"Task list {operation.list_id} not found")
    return _new_task(
        db,
        task_list.graph_list_id,
        GraphTaskCreate(
            title=operation.title,
            body={"contentType": "text", "content": operation.description},
            importance=operation.priority,
        ),
    )


def _update_backlog_item(db: Session, item: TriggerScrumItem, operation: UpdateScrumItem) -> None:
    task = _ensure_task(db, item.graph_list_id, item.graph_task_id)
    changes = {}
    if operation.title is not None:
        changes["title"] = operation.title
    if "description" in operation.model_fields_set:
        changes["body"] = {"contentType": "text", "content": operation.description}
    if operation.priority is not None:
        changes["importance"] = operation.priority
    if changes:
        _apply_task_update(db, task, GraphTaskUpdate(**changes))
    if operation.points is not None:
        item.points = operation.points
    if operation.status is not None:
        item.status = operation.status
        _sync_task_workflow(task, item.status)
    item.updated_at = datetime.now(timezone.utc)


def _apply_item_operation(
    db: Session,
    scrum: TriggerScrum,
    operation: ScrumItemOperation,
    destination: TriggerScrum | None,
) -> TriggerScrumItem:
    if isinstance(operation, (AddScrumItem, CreateScrumItem)):
        if isinstance(operation, AddScrumItem):
            task = _ensure_task(db, operation.list_id, operation.task_id)
            _ensure_task_not_in_scrum(db, scrum.id, task.graph_list_id, task.graph_task_id)
        else:
            task = _create_backlog_task(db, operation)
        status = operation.status or _task_item_status(task)
        if operation.status is not None:
            _sync_task_workflow(task, status)
        return _new_scrum_item(db, scrum, task, operation.points, status)

    item = _get_scrum_item(db, scrum.id, operation.item_id)
    if isinstance(operation, UpdateScrumItem):
        _update_backlog_item(db, item, operation)
    elif isinstance(operation, RemoveScrumItem):
        db.delete(item)
    elif isinstance(operation, MoveScrumItem):
        assert destination is not None  # Required by ScrumItemBatch.
        if item.status == "done":
            raise HTTPException(status_code=409, detail=f"Completed Scrum item {item.id} cannot be moved")
        _ensure_task(db, item.graph_list_id, item.graph_task_id)
        _ensure_task_not_in_scrum(db, destination.id, item.graph_list_id, item.graph_task_id)
        item.scrum_id = destination.id
        item.added_after_start = destination.status == "active"
    return item


def _recalculate_target(db: Session, scrum: TriggerScrum) -> None:
    scrum.target_points = db.scalar(
        select(func.coalesce(func.sum(TriggerScrumItem.points), 0)).where(TriggerScrumItem.scrum_id == scrum.id)
    )
    scrum.updated_at = datetime.now(timezone.utc)


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
    start_date, end_date = _clean(payload.start_date), _clean(payload.end_date)
    _check_scrum_dates(start_date, end_date)
    _lock_scrum_writes(db)
    if status == "active":
        _ensure_single_active(db)

    row = TriggerScrum(
        name=name,
        goal=_clean(payload.goal),
        start_date=start_date,
        end_date=end_date,
        target_points=_points(payload.target_points),
        status=status,
        completed_at=datetime.now(timezone.utc) if status == "completed" else None,
    )
    db.add(row)
    db.flush()
    _replace_items(db, row, payload.items, mark_new_after_start=False)
    row.target_points = sum(_points(item.points) for item in payload.items)
    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.patch("/{scrum_id}")
def update_scrum(scrum_id: int, payload: TriggerScrumUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    _lock_scrum_writes(db)
    row = _get_scrum_for_write(db, scrum_id)

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
    if "start_date" in data or "end_date" in data:
        _check_scrum_dates(row.start_date, row.end_date)
    if "target_points" in data:
        row.target_points = _points(data.get("target_points"))
    if "status" in data:
        status = _normalize_scrum_status(data.get("status"))
        if status == "active":
            _ensure_single_active(db, scrum_id=row.id)
        row.status = status
        if status == "completed" and row.completed_at is None:
            row.completed_at = datetime.now(timezone.utc)
        elif status != "completed":
            row.completed_at = None
    if payload.items is not None:
        _replace_items(db, row, payload.items)
        row.target_points = sum(_points(item.points) for item in payload.items)

    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.post("/{scrum_id}/start")
def start_scrum(scrum_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request
    _lock_scrum_writes(db)
    row = _get_scrum_for_write(db, scrum_id)
    _ensure_single_active(db, scrum_id=row.id)
    row.status = "active"
    row.completed_at = None
    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.post("/{scrum_id}/complete")
def complete_scrum(scrum_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request
    _lock_scrum_writes(db)
    row = _get_scrum_for_write(db, scrum_id)
    row.status = "completed"
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@internal_router.post("/{scrum_id}/items", response_model=ScrumItemBatchResult)
def manage_scrum_items(
    scrum_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    payload: ScrumItemBatch,
    db: Session = Depends(get_db),
) -> ScrumItemBatchResult:
    destination_id = payload.destination_scrum_id
    if destination_id == scrum_id:
        raise HTTPException(status_code=400, detail="The destination Sprint must differ from the source Sprint")

    try:
        with db.begin():
            _lock_scrum_writes(db)
            scrum_ids = [scrum_id] if destination_id is None else sorted([scrum_id, destination_id])
            scrums = {row_id: _get_scrum_for_write(db, row_id) for row_id in scrum_ids}
            scrum = scrums[scrum_id]
            destination = scrums.get(destination_id)
            if destination is not None and destination.status == "completed":
                raise HTTPException(status_code=409, detail="The destination Sprint is completed")

            results = []
            for index, operation in enumerate(payload.operations):
                try:
                    item = _apply_item_operation(db, scrum, operation, destination)
                    db.flush()
                except HTTPException as exc:
                    raise HTTPException(status_code=exc.status_code, detail=f"operations[{index}]: {exc.detail}") from exc
                results.append({
                    "action": operation.action,
                    "item_id": item.id,
                    "list_id": item.graph_list_id,
                    "task_id": item.graph_task_id,
                })

            for row in scrums.values():
                _recalculate_target(db, row)
            db.flush()
            result = ScrumItemBatchResult(
                scrum=_serialize(scrum, db),
                destination_scrum=_serialize(destination, db) if destination is not None else None,
                results=results,
            )
        return result
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Scrum or task membership changed during the batch") from exc
    except OperationalError as exc:
        if db.get_bind().dialect.name == "sqlite" and "database is locked" in str(exc.orig):
            raise HTTPException(status_code=409, detail="TriggerToDo is busy. The batch was rolled back") from exc
        raise


@router.patch("/{scrum_id}/items/{item_id}")
def update_scrum_item(
    scrum_id: int,
    item_id: int,
    payload: TriggerScrumItemStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _ = request
    _lock_scrum_writes(db)
    scrum = _get_scrum_for_write(db, scrum_id)
    item = _get_scrum_item(db, scrum_id, item_id)
    item.status = _normalize_item_status(payload.status)
    _sync_task_workflow(_ensure_task(db, item.graph_list_id, item.graph_task_id), item.status)
    db.commit()
    db.refresh(scrum)
    return _serialize(scrum, db)
