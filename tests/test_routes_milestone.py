from app.models import TodoTaskCache, TriggerEpic
from app.routes_milestone import create_milestone, delete_milestone, list_milestones, update_milestone
from app.schemas import TriggerMilestoneCreate, TriggerMilestoneUpdate


def test_create_and_list_milestone_with_links(db_session) -> None:
    db_session.add(TriggerEpic(epic_key="EPIC-1", name="Launch", status="Open", priority="P1"))
    db_session.add(
        TodoTaskCache(
            graph_list_id="list-1",
            graph_task_id="task-1",
            title="Prepare launch",
            status="notStarted",
            raw_json="{}",
            deleted=False,
        )
    )
    db_session.commit()

    created = create_milestone(
        TriggerMilestoneCreate(
            title="Launch window",
            milestone_at="2026-05-20T09:00",
            location="Toronto",
            epic_keys=["epic-1"],
            task_ids=["task-1"],
        ),
        request=None,
        db=db_session,
    )

    assert created["title"] == "Launch window"
    assert created["epic_keys"] == ["EPIC-1"]
    assert created["summary"] == {"epics": 1, "tasks": 1}
    assert created["epics"][0]["name"] == "Launch"
    assert created["tasks"][0]["title"] == "Prepare launch"

    listed = list_milestones(request=None, db=db_session)
    assert listed["count"] == 1
    assert listed["items"][0]["location"] == "Toronto"


def test_update_milestone_replaces_links(db_session) -> None:
    created = create_milestone(
        TriggerMilestoneCreate(title="Draft", epic_keys=["EPIC-1"], task_ids=["task-1"]),
        request=None,
        db=db_session,
    )

    updated = update_milestone(
        created["id"],
        TriggerMilestoneUpdate(title="Final", epic_keys=["EPIC-2"], task_ids=[]),
        request=None,
        db=db_session,
    )

    assert updated["title"] == "Final"
    assert updated["epic_keys"] == ["EPIC-2"]
    assert updated["task_ids"] == []


def test_delete_milestone_removes_row(db_session) -> None:
    created = create_milestone(TriggerMilestoneCreate(title="Temporary"), request=None, db=db_session)

    assert delete_milestone(created["id"], request=None, db=db_session) == {"ok": True}
    assert list_milestones(request=None, db=db_session) == {"count": 0, "items": []}


def test_list_milestones_sorts_newest_first(db_session) -> None:
    create_milestone(
        TriggerMilestoneCreate(title="Older", milestone_at="2026-05-01T09:00"),
        request=None,
        db=db_session,
    )
    create_milestone(
        TriggerMilestoneCreate(title="Newer", milestone_at="2026-06-01T09:00"),
        request=None,
        db=db_session,
    )

    listed = list_milestones(request=None, db=db_session)

    assert [item["title"] for item in listed["items"]] == ["Newer", "Older"]
