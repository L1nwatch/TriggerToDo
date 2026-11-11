import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TodoListCache, TodoTaskCache
from app.routes_scrum import create_scrum, list_scrums, manage_scrum_items, update_scrum
from app.routes_todo import query_cached_tasks
from app.schemas import TriggerScrumCreate, TriggerScrumItemCreate, TriggerScrumUpdate
from app.scrum_contract import ScrumItemBatch


def _task(db_session, list_id: str, task_id: str) -> None:
    db_session.add(
        TodoTaskCache(
            graph_list_id=list_id,
            graph_task_id=task_id,
            title=task_id,
            status="notStarted",
            raw_json="{}",
        )
    )
    db_session.commit()


def test_create_scrum_sums_item_points(db_session) -> None:
    _task(db_session, "list-1", "task-1")
    _task(db_session, "list-1", "task-2")

    created = create_scrum(
        TriggerScrumCreate(
            name="Sprint",
            target_points=99,
            items=[
                TriggerScrumItemCreate(list_id="list-1", task_id="task-1", points=3),
                TriggerScrumItemCreate(list_id="list-1", task_id="task-2", points=5),
            ],
        ),
        None,
        db_session,
    )

    assert created["target_points"] == 8
    assert created["summary"]["points"] == 8
    assert created["goal"] is None


def test_update_scrum_recalculates_points_when_items_change(db_session) -> None:
    _task(db_session, "list-1", "task-1")
    created = create_scrum(
        TriggerScrumCreate(
            name="Sprint",
            items=[TriggerScrumItemCreate(list_id="list-1", task_id="task-1", points=3)],
        ),
        None,
        db_session,
    )

    updated = update_scrum(
        created["id"],
        TriggerScrumUpdate(
            target_points=99,
            items=[TriggerScrumItemCreate(list_id="list-1", task_id="task-1", points=8)],
        ),
        None,
        db_session,
    )

    assert updated["target_points"] == 8
    assert updated["summary"]["points"] == 8


def _manage(db_session, scrum_id, operations, destination_scrum_id=None):
    with Session(db_session.get_bind(), autoflush=False) as db:
        return manage_scrum_items(
            scrum_id,
            ScrumItemBatch(operations=operations, destination_scrum_id=destination_scrum_id),
            db,
        )


def test_manage_backlog_and_verify_saved_scrums(db_session) -> None:
    _task(db_session, "list-1", "task-1")
    source = create_scrum(
        TriggerScrumCreate(name="Next week", goal="Initial goal", start_date="2026-11-16", end_date="2026-11-20"),
        None,
        db_session,
    )["id"]
    destination = create_scrum(TriggerScrumCreate(name="Following week"), None, db_session)["id"]

    batch = _manage(db_session, source, [
        {"action": "add", "list_id": "list-1", "task_id": "task-1", "points": 3},
        {"action": "create", "title": "New story", "description": "Original notes", "priority": "normal", "points": 5},
        {"action": "create", "title": "Later story", "points": 2},
    ])
    assert [result.action for result in batch.results] == ["add", "create", "create"]
    existing, created, removed = batch.results
    assert existing.task_id == "task-1"
    assert created.list_id == removed.list_id == "local-list-inbox"
    assert batch.scrum.summary.points == batch.scrum.target_points == 10

    _manage(db_session, source, [
        {"action": "update", "item_id": existing.item_id, "status": "done", "points": 4},
        {
            "action": "update", "item_id": created.item_id, "status": "doing", "title": "Edited story",
            "description": None, "priority": "high", "points": 8,
        },
        {"action": "remove", "item_id": removed.item_id},
    ])
    updated = update_scrum(source, TriggerScrumUpdate(
        name="Delivery Sprint", goal="Updated goal", end_date="2026-11-21", status="active",
    ), None, db_session)
    assert updated["start_date"] == "2026-11-16"
    assert updated["status"] == "active"

    moved = _manage(db_session, source, [{"action": "move", "item_id": created.item_id}], destination)
    assert moved.scrum.target_points == moved.scrum.summary.done_points == 4
    assert moved.destination_scrum.target_points == 8
    assert moved.destination_scrum.items[0].id == created.item_id
    assert moved.destination_scrum.items[0].status == "doing"

    persisted = {scrum["id"]: scrum for scrum in list_scrums(None, db_session)["items"]}
    assert persisted[source]["name"] == "Delivery Sprint"
    assert persisted[source]["goal"] == "Updated goal"
    assert persisted[source]["end_date"] == "2026-11-21"
    assert [item["id"] for item in persisted[source]["items"]] == [existing.item_id]
    story = persisted[destination]["items"][0]
    assert (story["points"], story["status"]) == (8, "doing")
    assert (story["task"]["title"], story["task"]["description"], story["task"]["importance"]) == (
        "Edited story", None, "high",
    )
    tasks = {task["taskId"]: task for task in query_cached_tasks(None, db_session, None, None, False)["items"]}
    assert tasks[existing.task_id]["status"] == "completed"
    assert tasks[created.task_id]["wfStatus"] == "doing"
    assert removed.task_id in tasks


def test_batch_rolls_back_new_task_default_list_and_membership_on_conflict(db_session) -> None:
    _task(db_session, "list-1", "task-1")
    scrum_id = create_scrum(TriggerScrumCreate(name="Sprint"), None, db_session)["id"]
    add = {"action": "add", "list_id": "list-1", "task_id": "task-1", "status": "done"}
    with pytest.raises(HTTPException, match=r"operations\[2\].*already in Scrum") as error:
        _manage(db_session, scrum_id, [{"action": "create", "title": "Rolled back"}, add, add])
    assert error.value.status_code == 409
    assert list_scrums(None, db_session)["items"][0]["items"] == []
    assert db_session.scalars(select(TodoListCache)).all() == []
    tasks = db_session.scalars(select(TodoTaskCache)).all()
    assert [(task.graph_task_id, task.status) for task in tasks] == [("task-1", "notStarted")]


def test_invalid_partial_dates_and_completed_item_moves_are_rejected(db_session) -> None:
    source = create_scrum(TriggerScrumCreate(
        name="First Sprint", start_date="2026-11-16", end_date="2026-11-20", status="active",
    ), None, db_session)["id"]
    destination = create_scrum(TriggerScrumCreate(name="Following Sprint"), None, db_session)["id"]
    with pytest.raises(HTTPException, match="start_date must be on or before end_date"):
        update_scrum(source, TriggerScrumUpdate(end_date="2026-11-15"), None, db_session)
    db_session.rollback()
    with pytest.raises(HTTPException, match="Another scrum is already active"):
        update_scrum(destination, TriggerScrumUpdate(status="active"), None, db_session)
    db_session.rollback()
    added = _manage(db_session, source, [{"action": "create", "title": "Done story", "status": "done"}])
    with pytest.raises(HTTPException, match="cannot be moved") as error:
        _manage(db_session, source, [{"action": "move", "item_id": added.results[0].item_id}], destination)
    assert error.value.status_code == 409
    scrums = {scrum["id"]: scrum for scrum in list_scrums(None, db_session)["items"]}
    assert scrums[source]["end_date"] == "2026-11-20"
    assert scrums[source]["summary"]["count_by_status"]["done"] == 1
    assert scrums[destination]["items"] == []
