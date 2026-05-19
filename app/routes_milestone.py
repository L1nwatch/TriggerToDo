from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TodoTaskCache, TriggerEpic, TriggerMilestone, TriggerMilestoneLink
from app.schemas import TriggerMilestoneCreate, TriggerMilestoneUpdate

router = APIRouter(prefix="/api/milestones", tags=["milestones"])


def _clean_ref(value: str) -> str:
    return str(value or "").strip()


def _clean_epic_key(value: str) -> str:
    return _clean_ref(value).upper()


def _replace_links(db: Session, milestone_id: int, link_type: str, values: list[str]) -> None:
    db.query(TriggerMilestoneLink).filter(
        TriggerMilestoneLink.milestone_id == milestone_id,
        TriggerMilestoneLink.link_type == link_type,
    ).delete()

    clean_values = []
    for value in values:
        clean = _clean_epic_key(value) if link_type == "epic" else _clean_ref(value)
        if clean and clean not in clean_values:
            clean_values.append(clean)

    for ref_id in clean_values:
        db.add(TriggerMilestoneLink(milestone_id=milestone_id, link_type=link_type, ref_id=ref_id))


def _serialize(row: TriggerMilestone, db: Session) -> dict:
    links = (
        db.query(TriggerMilestoneLink)
        .filter(TriggerMilestoneLink.milestone_id == row.id)
        .order_by(TriggerMilestoneLink.link_type.asc(), TriggerMilestoneLink.ref_id.asc())
        .all()
    )
    epic_keys = [link.ref_id for link in links if link.link_type == "epic"]
    task_ids = [link.ref_id for link in links if link.link_type == "task"]

    epics_by_key = {}
    if epic_keys:
        epics = db.query(TriggerEpic).filter(TriggerEpic.epic_key.in_(epic_keys)).all()
        epics_by_key = {epic.epic_key: epic for epic in epics}

    tasks_by_id = {}
    if task_ids:
        tasks = (
            db.query(TodoTaskCache)
            .filter(TodoTaskCache.graph_task_id.in_(task_ids), TodoTaskCache.deleted.is_(False))
            .order_by(TodoTaskCache.updated_at.desc())
            .all()
        )
        for task in tasks:
            tasks_by_id.setdefault(task.graph_task_id, task)

    epic_items = [
        {
            "epic_key": key,
            "name": epics_by_key[key].name if key in epics_by_key else key,
            "status": epics_by_key[key].status if key in epics_by_key else None,
            "priority": epics_by_key[key].priority if key in epics_by_key else None,
        }
        for key in epic_keys
    ]
    task_items = [
        {
            "task_id": task_id,
            "list_id": tasks_by_id[task_id].graph_list_id if task_id in tasks_by_id else None,
            "title": tasks_by_id[task_id].title if task_id in tasks_by_id else task_id,
            "status": tasks_by_id[task_id].status if task_id in tasks_by_id else None,
            "due_datetime": tasks_by_id[task_id].due_datetime if task_id in tasks_by_id else None,
        }
        for task_id in task_ids
    ]

    return {
        "id": row.id,
        "title": row.title,
        "milestone_at": row.milestone_at,
        "location": row.location,
        "notes": row.notes,
        "updated_at": row.updated_at,
        "epic_keys": epic_keys,
        "task_ids": task_ids,
        "summary": {
            "epics": len(epic_keys),
            "tasks": len(task_ids),
        },
        "epics": epic_items,
        "tasks": task_items,
    }


@router.get("")
def list_milestones(request: Request, db: Session = Depends(get_db)):
    _ = request
    rows = db.query(TriggerMilestone).order_by(TriggerMilestone.milestone_at.desc(), TriggerMilestone.id.desc()).all()
    return {"count": len(rows), "items": [_serialize(row, db) for row in rows]}


@router.post("")
def create_milestone(payload: TriggerMilestoneCreate, request: Request, db: Session = Depends(get_db)):
    _ = request
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Milestone title is required")

    row = TriggerMilestone(
        title=title,
        milestone_at=_clean_ref(payload.milestone_at) or None,
        location=_clean_ref(payload.location) or None,
        notes=_clean_ref(payload.notes) or None,
    )
    db.add(row)
    db.flush()
    _replace_links(db, row.id, "epic", payload.epic_keys)
    _replace_links(db, row.id, "task", payload.task_ids)
    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.patch("/{milestone_id}")
def update_milestone(
    milestone_id: int,
    payload: TriggerMilestoneUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    _ = request
    row = db.query(TriggerMilestone).filter(TriggerMilestone.id == milestone_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Milestone not found")

    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        title = str(data["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="Milestone title is required")
        row.title = title
    if "milestone_at" in data:
        row.milestone_at = _clean_ref(data.get("milestone_at")) or None
    if "location" in data:
        row.location = _clean_ref(data.get("location")) or None
    if "notes" in data:
        row.notes = _clean_ref(data.get("notes")) or None
    if "epic_keys" in data:
        _replace_links(db, row.id, "epic", data.get("epic_keys") or [])
    if "task_ids" in data:
        _replace_links(db, row.id, "task", data.get("task_ids") or [])

    db.commit()
    db.refresh(row)
    return _serialize(row, db)


@router.delete("/{milestone_id}")
def delete_milestone(milestone_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerMilestone).filter(TriggerMilestone.id == milestone_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Milestone not found")

    db.query(TriggerMilestoneLink).filter(TriggerMilestoneLink.milestone_id == milestone_id).delete()
    db.delete(row)
    db.commit()
    return {"ok": True}
