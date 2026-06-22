from app.models import TodoTaskCache
from app.routes_scrum import create_scrum, update_scrum
from app.schemas import TriggerScrumCreate, TriggerScrumItemCreate, TriggerScrumUpdate


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
