#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db import Base, SessionLocal, engine
from app.models import TodoListCache, TodoTaskCache, TriggerEpic, TriggerEvent, TriggerRule


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import local bootstrap data from initialize_data.json.")
    parser.add_argument(
        "--file",
        default="initialize_data.json",
        help="Path to initialize JSON payload. Default: initialize_data.json",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing local data for the target user before import.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Input JSON not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("Top-level JSON must be an object.")
    return payload


def _safe_json_dumps(value: Any) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except json.JSONDecodeError:
            return json.dumps({"value": value})
    return json.dumps(value)


def _replace_existing(db) -> None:
    db.query(TodoTaskCache).delete()
    db.query(TodoListCache).delete()
    db.query(TriggerEpic).delete()
    db.query(TriggerRule).delete()
    db.query(TriggerEvent).delete()
    db.commit()


def _import_lists(db, items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        list_id = str(item.get("graph_list_id") or item.get("id") or "").strip()
        if not list_id:
            continue
        display_name = str(item.get("display_name") or item.get("displayName") or list_id)
        row = (
            db.query(TodoListCache)
            .filter(TodoListCache.graph_list_id == list_id)
            .first()
        )
        if row:
            row.display_name = display_name
            row.is_owner = bool(item.get("is_owner", True))
            row.is_shared = bool(item.get("is_shared", False))
            row.etag = item.get("etag")
        else:
            db.add(
                TodoListCache(
                    graph_list_id=list_id,
                    display_name=display_name,
                    is_owner=bool(item.get("is_owner", True)),
                    is_shared=bool(item.get("is_shared", False)),
                    etag=item.get("etag"),
                )
            )
        count += 1
    db.commit()
    return count


def _import_tasks(db, items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        list_id = str(item.get("graph_list_id") or item.get("listId") or "").strip()
        task_id = str(item.get("graph_task_id") or item.get("taskId") or item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not list_id or not task_id or not title:
            continue

        row = (
            db.query(TodoTaskCache)
            .filter(
                TodoTaskCache.graph_list_id == list_id,
                TodoTaskCache.graph_task_id == task_id,
            )
            .first()
        )
        if not row:
            row = TodoTaskCache(
                graph_list_id=list_id,
                graph_task_id=task_id,
                title=title,
                raw_json="{}",
                deleted=False,
            )
            db.add(row)

        row.title = title
        row.body_content = item.get("body_content") or item.get("bodyContent")
        row.importance = item.get("importance")
        row.status = item.get("status")
        row.due_datetime = item.get("due_datetime") or item.get("dueDateTime")
        row.due_timezone = item.get("due_timezone") or item.get("dueTimeZone")

        recurrence = item.get("recurrence_json")
        if recurrence is None and item.get("recurrenceJson") is not None:
            recurrence = item.get("recurrenceJson")
        row.recurrence_json = _safe_json_dumps(recurrence) if recurrence is not None else None

        row.pool = item.get("pool")
        row.wf_status = item.get("wf_status") or item.get("wfStatus")
        row.trigger_ref = item.get("trigger_ref") or item.get("triggerRef")
        row.raw_json = _safe_json_dumps(item.get("raw_json") or item.get("rawJson") or {})
        row.deleted = bool(item.get("deleted", False))
        count += 1

    db.commit()
    return count


def _import_epics(db, items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        epic_key = str(item.get("epic_key") or item.get("epicKey") or item.get("key") or "").strip().upper()
        name = str(item.get("name") or item.get("summary") or epic_key).strip()
        if not epic_key:
            continue
        row = (
            db.query(TriggerEpic)
            .filter(TriggerEpic.epic_key == epic_key)
            .first()
        )
        if row:
            row.name = name
            row.status = item.get("status")
            row.priority = item.get("priority")
        else:
            db.add(
                TriggerEpic(
                    epic_key=epic_key,
                    name=name,
                    status=item.get("status"),
                    priority=item.get("priority"),
                )
            )
        count += 1
    db.commit()
    return count


def _import_rules(db, items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        row = TriggerRule(
            name=name,
            source_pool=item.get("source_pool"),
            source_wf_status=item.get("source_wf_status"),
            target_pool=item.get("target_pool"),
            target_wf_status=item.get("target_wf_status"),
            enabled=bool(item.get("enabled", True)),
            cron_expression=item.get("cron_expression"),
        )
        db.add(row)
        count += 1
    db.commit()
    return count


def _import_events(db, items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        row = TriggerEvent(
            name=name,
            is_active=bool(item.get("is_active", False)),
        )
        db.add(row)
        count += 1
    db.commit()
    return count


def _as_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key) or []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def main() -> None:
    args = parse_args()
    payload = _load_json(Path(args.file))

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.replace:
            _replace_existing(db)

        list_count = _import_lists(db, _as_list(payload, "todo_lists"))
        task_count = _import_tasks(db, _as_list(payload, "todo_tasks"))
        epic_count = _import_epics(db, _as_list(payload, "trigger_epics"))
        rule_count = _import_rules(db, _as_list(payload, "trigger_rules"))
        event_count = _import_events(db, _as_list(payload, "trigger_events"))

    print(
        "[import-json] done "
        f"lists={list_count} tasks={task_count} "
        f"epics={epic_count} rules={rule_count} events={event_count}"
    )


if __name__ == "__main__":
    main()
