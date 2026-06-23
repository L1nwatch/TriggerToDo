from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TriggerRoutineCheck
from app.schemas import TriggerRoutineCheckUpdate

router = APIRouter(prefix="/api/routines", tags=["routines"])


def _parse_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}") from None


def _serialize(row: TriggerRoutineCheck) -> dict:
    return {
        "id": row.id,
        "list_id": row.graph_list_id,
        "task_id": row.graph_task_id,
        "check_date": row.check_date,
        "updated_at": row.updated_at,
    }


@router.get("/checks")
def list_routine_checks(
    request: Request,
    db: Session = Depends(get_db),
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    _ = request
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    rows = (
        db.query(TriggerRoutineCheck)
        .filter(
            TriggerRoutineCheck.check_date >= start,
            TriggerRoutineCheck.check_date <= end,
        )
        .order_by(TriggerRoutineCheck.check_date.asc(), TriggerRoutineCheck.id.asc())
        .all()
    )
    return {"count": len(rows), "items": [_serialize(row) for row in rows]}


@router.put("/checks")
def set_routine_check(payload: TriggerRoutineCheckUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    list_id = payload.list_id.strip()
    task_id = payload.task_id.strip()
    check_date = _parse_date(payload.check_date, "check_date")
    if not list_id or not task_id:
        raise HTTPException(status_code=400, detail="Routine checks require list_id and task_id")

    row = (
        db.query(TriggerRoutineCheck)
        .filter(
            TriggerRoutineCheck.graph_list_id == list_id,
            TriggerRoutineCheck.graph_task_id == task_id,
            TriggerRoutineCheck.check_date == check_date,
        )
        .first()
    )

    if payload.checked:
        if not row:
            row = TriggerRoutineCheck(graph_list_id=list_id, graph_task_id=task_id, check_date=check_date)
            db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize(row)

    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}
