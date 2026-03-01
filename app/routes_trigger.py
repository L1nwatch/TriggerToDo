from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import TodoTaskCache, TriggerRule
from app.schemas import TriggerRuleCreate, TriggerRuleUpdate
from app.trigger_engine import TriggerEngine

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


def get_engine(request: Request) -> TriggerEngine:
    return request.app.state.trigger_engine


def _rule_to_dict(row: TriggerRule) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "source_pool": row.source_pool,
        "source_wf_status": row.source_wf_status,
        "target_pool": row.target_pool,
        "target_wf_status": row.target_wf_status,
        "enabled": row.enabled,
        "cron_expression": row.cron_expression,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_rules(request: Request, db: Session = Depends(get_db)):
    _ = request
    rows = db.query(TriggerRule).order_by(TriggerRule.id.desc()).all()
    return {"count": len(rows), "items": [_rule_to_dict(row) for row in rows]}


@router.post("")
def create_rule(payload: TriggerRuleCreate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = TriggerRule(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rule_to_dict(row)


@router.patch("/{rule_id}")
def update_rule(rule_id: int, payload: TriggerRuleUpdate, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerRule).filter(TriggerRule.id == rule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _rule_to_dict(row)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, request: Request, db: Session = Depends(get_db)):
    _ = request
    row = db.query(TriggerRule).filter(TriggerRule.id == rule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/run")
def run_now(request: Request, db: Session = Depends(get_db)):
    _ = request
    return get_engine(request).run_once_for_user(db)


@router.get("/monitor")
def monitor_rules(request: Request, db: Session = Depends(get_db)):
    _ = request
    rules = db.query(TriggerRule).order_by(TriggerRule.id.asc()).all()

    open_tasks = db.query(TodoTaskCache).filter(
        TodoTaskCache.deleted.is_(False),
        or_(TodoTaskCache.status.is_(None), TodoTaskCache.status != "completed"),
    )
    unassigned_count = open_tasks.filter(
        (TodoTaskCache.trigger_ref.is_(None)) | (TodoTaskCache.trigger_ref == "")
    ).count()

    rule_items = []
    for rule in rules:
        matches_query = open_tasks
        if rule.source_pool is not None:
            matches_query = matches_query.filter(TodoTaskCache.pool == rule.source_pool)
        if rule.source_wf_status is not None:
            matches_query = matches_query.filter(TodoTaskCache.wf_status == rule.source_wf_status)

        selected_query = open_tasks.filter(TodoTaskCache.trigger_ref == str(rule.id))
        selected_count = selected_query.count()
        due_signal_count = selected_query.filter(TodoTaskCache.due_datetime.is_not(None)).count()
        recurrence_signal_count = selected_query.filter(TodoTaskCache.recurrence_json.is_not(None)).count()

        last_signal = (
            selected_query.order_by(TodoTaskCache.updated_at.desc()).with_entities(TodoTaskCache.updated_at).first()
        )
        item = _rule_to_dict(rule)
        item["monitor"] = {
            "matchingTasks": matches_query.count(),
            "selectedTasks": selected_count,
            "dueSignals": due_signal_count,
            "recurrenceSignals": recurrence_signal_count,
            "lastSignalAt": last_signal[0] if last_signal else None,
        }
        rule_items.append(item)

    orphan_refs = (
        open_tasks.filter(TodoTaskCache.trigger_ref.is_not(None), TodoTaskCache.trigger_ref != "")
        .with_entities(TodoTaskCache.trigger_ref)
        .distinct()
        .all()
    )
    valid_ids = {str(rule.id) for rule in rules}
    orphans = [row[0] for row in orphan_refs if row[0] not in valid_ids]

    return {
        "count": len(rule_items),
        "items": rule_items,
        "unassignedTasks": unassigned_count,
        "orphanTriggerRefs": orphans,
    }


@router.post("/webhook")
def webhook(
    request: Request,
    x_trigger_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if x_trigger_secret != settings.trigger_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    engine = get_engine(request)
    engine.run_once_all_users()
    return {"ok": True}
