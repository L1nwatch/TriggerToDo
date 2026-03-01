import json

from app.models import TodoTaskCache, TriggerRule
from app.routes_todo import _task_payload_from_create
from app.routes_trigger import _rule_to_dict
from app.schemas import GraphTaskCreate
from app.trigger_engine import TriggerEngine


def test_task_payload_from_create_contains_open_extension() -> None:
    payload = GraphTaskCreate(
        title="Task",
        extensions={"pool": "inbox", "wfStatus": "todo", "triggerRef": "r1"},
    )
    body = _task_payload_from_create(payload)

    assert body["title"] == "Task"
    assert "extensions" in body
    assert body["extensions"][0]["extensionName"] == "com.triggertodo.meta"


def test_rule_to_dict_contains_expected_fields(db_session) -> None:
    row = TriggerRule(
        name="Promote",
        source_pool="inbox",
        source_wf_status="todo",
        target_pool="today",
        target_wf_status="doing",
        enabled=True,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    data = _rule_to_dict(row)
    assert data["id"] == row.id
    assert data["name"] == "Promote"
    assert data["target_pool"] == "today"


def test_trigger_engine_moves_matching_tasks(db_session, monkeypatch) -> None:
    rule = TriggerRule(
        name="Move backlog",
        source_pool="backlog",
        source_wf_status="queued",
        target_pool="today",
        target_wf_status="active",
        enabled=True,
    )
    db_session.add(rule)
    db_session.flush()

    task = TodoTaskCache(
        graph_list_id="list-1",
        graph_task_id="task-1",
        title="Task",
        pool="backlog",
        wf_status="queued",
        trigger_ref=None,
        raw_json=json.dumps(
            {
                "extensions": [
                    {
                        "id": "ext-123",
                        "extensionName": "com.triggertodo.meta",
                        "pool": "backlog",
                        "wfStatus": "queued",
                    }
                ]
            }
        ),
        deleted=False,
    )
    db_session.add(task)
    db_session.commit()

    engine = TriggerEngine(interval_seconds=30)
    result = engine.run_once_for_user(db_session)

    assert result == {"moved": 1}
    db_session.refresh(task)
    assert task.pool == "today"
    assert task.wf_status == "active"
    assert task.trigger_ref == str(rule.id)

    raw = json.loads(task.raw_json)
    ext = next(item for item in raw["extensions"] if item.get("extensionName") == "com.triggertodo.meta")
    assert ext["pool"] == "today"
    assert ext["wfStatus"] == "active"
    assert ext["triggerRef"] == str(rule.id)
