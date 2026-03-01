#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db import SessionLocal
from app.models import TodoListCache, TodoTaskCache, TriggerEpic, TriggerEvent, TriggerRule


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export local bootstrap data to initialize_data.json.")
    parser.add_argument(
        "--file",
        default="initialize_data.json",
        help="Output JSON path. Default: initialize_data.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with SessionLocal() as db:
        lists = (
            db.query(TodoListCache)
            .order_by(TodoListCache.graph_list_id.asc())
            .all()
        )
        tasks = (
            db.query(TodoTaskCache)
            .order_by(TodoTaskCache.graph_list_id.asc(), TodoTaskCache.graph_task_id.asc())
            .all()
        )
        epics = (
            db.query(TriggerEpic)
            .order_by(TriggerEpic.epic_key.asc())
            .all()
        )
        rules = db.query(TriggerRule).order_by(TriggerRule.id.asc()).all()
        events = db.query(TriggerEvent).order_by(TriggerEvent.id.asc()).all()

    payload = {
        "todo_lists": [
            {
                "graph_list_id": row.graph_list_id,
                "display_name": row.display_name,
                "is_owner": row.is_owner,
                "is_shared": row.is_shared,
                "etag": row.etag,
            }
            for row in lists
        ],
        "todo_tasks": [
            {
                "graph_list_id": row.graph_list_id,
                "graph_task_id": row.graph_task_id,
                "title": row.title,
                "body_content": row.body_content,
                "importance": row.importance,
                "status": row.status,
                "due_datetime": row.due_datetime,
                "due_timezone": row.due_timezone,
                "recurrence_json": row.recurrence_json,
                "pool": row.pool,
                "wf_status": row.wf_status,
                "trigger_ref": row.trigger_ref,
                "raw_json": row.raw_json,
                "deleted": row.deleted,
            }
            for row in tasks
        ],
        "trigger_epics": [
            {
                "epic_key": row.epic_key,
                "name": row.name,
                "status": row.status,
                "priority": row.priority,
            }
            for row in epics
        ],
        "trigger_rules": [
            {
                "name": row.name,
                "source_pool": row.source_pool,
                "source_wf_status": row.source_wf_status,
                "target_pool": row.target_pool,
                "target_wf_status": row.target_wf_status,
                "enabled": row.enabled,
                "cron_expression": row.cron_expression,
            }
            for row in rules
        ],
        "trigger_events": [
            {
                "name": row.name,
                "is_active": row.is_active,
            }
            for row in events
        ],
    }

    output = Path(args.file)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "[export-json] done "
        f"lists={len(payload['todo_lists'])} tasks={len(payload['todo_tasks'])} "
        f"epics={len(payload['trigger_epics'])} rules={len(payload['trigger_rules'])} "
        f"events={len(payload['trigger_events'])} file={output}"
    )


if __name__ == "__main__":
    main()
