from app.models import DeltaState, TodoListCache, TodoTaskCache
from app.sync import DeltaSyncService


def test_delta_sync_service_updates_local_cache(db_session, monkeypatch) -> None:
    class FakeGraphClient:
        def __init__(self, db):
            self.db = db

        def list_delta(self, _user_oid, _delta_link=None):
            return {
                "value": [
                    {"id": "list-1", "displayName": "Inbox", "@odata.etag": "etag-1"},
                ],
                "@odata.deltaLink": "lists-delta-token",
            }

        def task_delta(self, _user_oid, list_id, _delta_link=None):
            assert list_id == "list-1"
            return {
                "value": [
                    {
                        "id": "task-1",
                        "title": "Do thing",
                        "status": "notStarted",
                        "body": {"content": "Details"},
                        "importance": "normal",
                        "createdDateTime": "2026-03-01T10:00:00Z",
                        "lastModifiedDateTime": "2026-03-01T10:00:00Z",
                        "dueDateTime": {"dateTime": "2026-03-01T10:00:00", "timeZone": "UTC"},
                        "extensions": [
                            {
                                "extensionName": "com.triggertodo.meta",
                                "pool": "inbox",
                                "wfStatus": "todo",
                                "triggerRef": "ref-1",
                            }
                        ],
                    }
                ],
                "@odata.deltaLink": "tasks-delta-token",
            }

    monkeypatch.setattr("app.sync.GraphClient", FakeGraphClient)

    result = DeltaSyncService(db_session).run_for_user()
    assert result == {"listsSynced": 1, "tasksSynced": 1}

    lists = db_session.query(TodoListCache).all()
    assert len(lists) == 1
    assert lists[0].display_name == "Inbox"

    tasks = db_session.query(TodoTaskCache).all()
    assert len(tasks) == 1
    assert tasks[0].title == "Do thing"
    assert tasks[0].pool == "inbox"
    assert tasks[0].wf_status == "todo"
    assert tasks[0].trigger_ref == "ref-1"

    states = db_session.query(DeltaState).all()
    assert len(states) == 2


def test_delta_sync_preserves_existing_fields_on_partial_task_payload(db_session, monkeypatch) -> None:
    calls = {"task": 0}

    class FakeGraphClient:
        def __init__(self, db):
            self.db = db

        def list_delta(self, _user_oid, delta_link=None):
            if delta_link:
                return {"value": [], "@odata.deltaLink": "lists-delta-token-2"}
            return {
                "value": [
                    {"id": "list-1", "displayName": "Inbox", "@odata.etag": "etag-1"},
                ],
                "@odata.deltaLink": "lists-delta-token-1",
            }

        def task_delta(self, _user_oid, list_id, _delta_link=None):
            assert list_id == "list-1"
            calls["task"] += 1
            if calls["task"] == 1:
                return {
                    "value": [
                            {
                                "id": "task-1",
                                "title": "Original title",
                                "status": "notStarted",
                                "body": {"content": "Details"},
                                "importance": "normal",
                                "createdDateTime": "2026-03-01T10:00:00Z",
                                "lastModifiedDateTime": "2026-03-01T10:00:00Z",
                                "dueDateTime": {"dateTime": "2026-03-01T10:00:00", "timeZone": "UTC"},
                                "extensions": [
                                {
                                    "extensionName": "com.triggertodo.meta",
                                    "pool": "triggered",
                                    "wfStatus": "todo",
                                    "triggerRef": "ref-1",
                                }
                            ],
                        }
                    ],
                    "@odata.deltaLink": "tasks-delta-token-1",
                }
            return {
                "value": [
                    {
                        "id": "task-1",
                        "title": "Updated title",
                        "status": "notStarted",
                        "lastModifiedDateTime": "2026-03-01T12:00:00Z",
                    }
                ],
                "@odata.deltaLink": "tasks-delta-token-2",
            }

    monkeypatch.setattr("app.sync.GraphClient", FakeGraphClient)

    service = DeltaSyncService(db_session)
    service.run_for_user()
    service.run_for_user()

    task = db_session.query(TodoTaskCache).one()
    assert task.title == "Updated title"
    assert task.due_datetime == "2026-03-01T10:00:00"
    assert task.due_timezone == "UTC"
    assert task.pool == "triggered"
    assert task.wf_status == "todo"
    assert task.trigger_ref == "ref-1"
