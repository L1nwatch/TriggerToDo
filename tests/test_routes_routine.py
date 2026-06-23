from app.routes_routine import list_routine_checks, set_routine_check
from app.schemas import TriggerRoutineCheckUpdate


def test_set_and_list_routine_check(db_session) -> None:
    created = set_routine_check(
        TriggerRoutineCheckUpdate(
            list_id="list-1",
            task_id="task-1",
            check_date="2026-06-22",
            checked=True,
        ),
        request=None,
        db=db_session,
    )

    assert created["list_id"] == "list-1"
    assert created["task_id"] == "task-1"
    assert created["check_date"] == "2026-06-22"

    listed = list_routine_checks(
        request=None,
        db=db_session,
        start_date="2026-06-22",
        end_date="2026-06-28",
    )

    assert listed["count"] == 1
    assert listed["items"][0]["check_date"] == "2026-06-22"


def test_unset_routine_check_removes_row(db_session) -> None:
    payload = TriggerRoutineCheckUpdate(
        list_id="list-1",
        task_id="task-1",
        check_date="2026-06-22",
        checked=True,
    )
    set_routine_check(payload, request=None, db=db_session)

    assert set_routine_check(payload.model_copy(update={"checked": False}), request=None, db=db_session) == {"ok": True}
    assert list_routine_checks(
        request=None,
        db=db_session,
        start_date="2026-06-22",
        end_date="2026-06-28",
    ) == {"count": 0, "items": []}
