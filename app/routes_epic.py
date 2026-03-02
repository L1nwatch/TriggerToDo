import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TriggerEpic
from app.schemas import TriggerEpicCreate, TriggerEpicUpdate

router = APIRouter(prefix="/api/epics", tags=["epics"])


def _normalize_key(value: str) -> str:
    return value.strip().upper()


def _next_auto_key(db: Session) -> str:
    rows = db.query(TriggerEpic.epic_key).all()
    highest = 0
    for (value,) in rows:
        text = str(value or "").upper()
        match = re.fullmatch(r"EPIC-(\d+)", text)
        if not match:
            continue
        highest = max(highest, int(match.group(1)))
    return f"EPIC-{highest + 1}"


def _serialize(row: TriggerEpic) -> dict:
    return {
        "id": row.id,
        "epic_key": row.epic_key,
        "name": row.name,
        "status": row.status,
        "priority": row.priority,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_epics(request: Request, db: Session = Depends(get_db)):
    _ = request
    rows = (
        db.query(TriggerEpic)
        .order_by(TriggerEpic.epic_key.asc())
        .all()
    )
    items = [_serialize(row) for row in rows]
    return {"count": len(items), "items": items}


@router.post("")
def create_epic(payload: TriggerEpicCreate, request: Request, db: Session = Depends(get_db)):
    _ = request
    requested_key = str(payload.epic_key or "").strip()
    key = _normalize_key(requested_key) if requested_key else _next_auto_key(db)
    row = (
        db.query(TriggerEpic)
        .filter(TriggerEpic.epic_key == key)
        .first()
    )
    if row:
        row.name = payload.name
        row.status = payload.status
        row.priority = payload.priority
    else:
        row = TriggerEpic(
            epic_key=key,
            name=payload.name,
            status=payload.status,
            priority=payload.priority,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.patch("/{epic_id}")
def update_epic(epic_id: int, payload: TriggerEpicUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = (
        db.query(TriggerEpic)
        .filter(TriggerEpic.id == epic_id)
        .first()
    )
    if not row:
        return {"detail": "Not found"}
    data = payload.model_dump(exclude_none=True)
    for field, value in data.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return _serialize(row)
