from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TriggerEvent
from app.schemas import TriggerEventCreate, TriggerEventUpdate

router = APIRouter(prefix="/api/events", tags=["events"])


def _event_to_dict(row: TriggerEvent) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "is_active": row.is_active,
        "occurred_at": row.occurred_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_events(request: Request, db: Session = Depends(get_db)):
    _ = request
    rows = db.query(TriggerEvent).order_by(TriggerEvent.id.desc()).all()
    return {"count": len(rows), "items": [_event_to_dict(row) for row in rows]}


@router.post("")
def create_event(payload: TriggerEventCreate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = TriggerEvent(name=payload.name.strip(), is_active=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _event_to_dict(row)


@router.patch("/{event_id}")
def update_event(event_id: int, payload: TriggerEventUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerEvent).filter(TriggerEvent.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    data = payload.model_dump(exclude_none=True)
    if "name" in data:
        row.name = str(data["name"]).strip()
    if "is_active" in data:
        next_active = bool(data["is_active"])
        row.is_active = next_active
        row.occurred_at = datetime.now(timezone.utc) if next_active else None

    db.commit()
    db.refresh(row)
    return _event_to_dict(row)


@router.delete("/{event_id}")
def delete_event(event_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerEvent).filter(TriggerEvent.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(row)
    db.commit()
    return {"ok": True}
