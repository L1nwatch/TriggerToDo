import json

from app.models import TodoListCache, TodoTaskCache, TriggerEpic, TriggerRule
from app.routes_todo import _epic_key_from_raw_json, _task_payload_from_create, complete_task, create_task, update_task
from app.routes_trigger import _rule_to_dict
from app.schemas import GraphTaskCreate, GraphTaskUpdate
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


def test_create_task_does_not_link_done_epic(db_session) -> None:
    db_session.add(TodoListCache(graph_list_id="list-1", display_name="Inbox"))
    db_session.add(TriggerEpic(epic_key="EPIC-1", name="Completed epic", status="Done"))
    db_session.commit()

    task = create_task(
        "list-1",
        GraphTaskCreate(title="Task", extensions={"epicKey": "EPIC-1", "wfStatus": "todo"}),
        request=None,
        db=db_session,
    )

    assert task["extensions"][0]["epicKey"] is None


def test_complete_recurring_task_does_not_clone_done_epic_link(db_session) -> None:
    db_session.add(TodoListCache(graph_list_id="list-1", display_name="Inbox"))
    db_session.add(TriggerEpic(epic_key="EPIC-1", name="Completed epic", status="Done"))
    task = TodoTaskCache(
        graph_list_id="list-1",
        graph_task_id="task-1",
        title="Task",
        status="notStarted",
        due_datetime="2026-05-09T00:00:00Z",
        due_timezone="UTC",
        recurrence_json=json.dumps({"pattern": {"type": "daily", "interval": 1}, "range": {"type": "noEnd"}}),
        pool="today",
        wf_status="todo",
        trigger_ref="date:daily",
        raw_json=json.dumps(
            {
                "extensions": [
                    {
                        "extensionName": "com.triggertodo.meta",
                        "pool": "today",
                        "wfStatus": "todo",
                        "triggerRef": "date:daily",
                        "source": "triggertodo",
                        "epicKey": "EPIC-1",
                    }
                ]
            }
        ),
        deleted=False,
    )
    db_session.add(task)
    db_session.commit()

    complete_task("list-1", "task-1", request=None, db=db_session)

    next_task = (
        db_session.query(TodoTaskCache)
        .filter(TodoTaskCache.graph_task_id != "task-1")
        .one()
    )
    assert _epic_key_from_raw_json(next_task.raw_json) is None


def test_update_task_does_not_link_done_epic(db_session) -> None:
    db_session.add(TodoListCache(graph_list_id="list-1", display_name="Inbox"))
    db_session.add(TriggerEpic(epic_key="EPIC-1", name="Completed epic", status="Done"))
    db_session.add(
        TodoTaskCache(
            graph_list_id="list-1",
            graph_task_id="task-1",
            title="Task",
            status="notStarted",
            raw_json=json.dumps({"extensions": [{"extensionName": "com.triggertodo.meta"}]}),
            deleted=False,
        )
    )
    db_session.commit()

    task = update_task(
        "list-1",
        "task-1",
        GraphTaskUpdate(extensions={"epicKey": "EPIC-1"}),
        request=None,
        db=db_session,
    )

    assert task["extensions"][0]["epicKey"] is None


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
