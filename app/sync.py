import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.graph import GraphClient, extract_open_extension
from app.models import DeltaState, TodoListCache, TodoTaskCache

IMPORT_CUTOFF_ISO = "2026-01-01T00:00:00Z"
IMPORT_CUTOFF_DT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _parse_graph_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _is_after_import_cutoff(task_payload: dict[str, Any]) -> bool:
    created = _parse_graph_dt(task_payload.get("createdDateTime"))
    modified = _parse_graph_dt(task_payload.get("lastModifiedDateTime"))
    return bool((created and created >= IMPORT_CUTOFF_DT) or (modified and modified >= IMPORT_CUTOFF_DT))


def _is_local_only_task(raw_json: str | None) -> bool:
    if not raw_json:
        return False
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return False
    for ext in raw.get("extensions") or []:
        if ext.get("extensionName") == "com.triggertodo.meta" and ext.get("source") == "triggertodo":
            return True
    return False


class DeltaSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.graph = GraphClient(db)

    def run_for_user(self, user_oid: str) -> dict[str, Any]:
        self._prune_old_cached_tasks(user_oid)
        synced_lists = self._sync_lists(user_oid)
        synced_tasks = 0

        list_rows = self.db.query(TodoListCache).filter(TodoListCache.user_oid == user_oid).all()
        for row in list_rows:
            synced_tasks += self._sync_tasks_for_list(user_oid, row.graph_list_id)

        return {"listsSynced": synced_lists, "tasksSynced": synced_tasks}

    def _prune_old_cached_tasks(self, user_oid: str) -> None:
        rows = self.db.query(TodoTaskCache).filter(TodoTaskCache.user_oid == user_oid).all()
        for row in rows:
            try:
                raw = json.loads(row.raw_json or "{}")
            except json.JSONDecodeError:
                raw = {}
            if not _is_after_import_cutoff(raw):
                self.db.delete(row)
        self.db.commit()

    def _get_delta_state(self, user_oid: str, resource_type: str, graph_list_id: str | None = None) -> DeltaState | None:
        return (
            self.db.query(DeltaState)
            .filter(
                DeltaState.user_oid == user_oid,
                DeltaState.resource_type == resource_type,
                DeltaState.graph_list_id == graph_list_id,
            )
            .first()
        )

    def _upsert_delta_state(self, user_oid: str, resource_type: str, delta_link: str, graph_list_id: str | None = None):
        row = self._get_delta_state(user_oid, resource_type, graph_list_id)
        if row:
            row.delta_link = delta_link
        else:
            self.db.add(
                DeltaState(
                    user_oid=user_oid,
                    graph_list_id=graph_list_id,
                    resource_type=resource_type,
                    delta_link=delta_link,
                )
            )

    def _sync_lists(self, user_oid: str) -> int:
        state = self._get_delta_state(user_oid, "lists", None)
        data = self.graph.list_delta(user_oid, state.delta_link if state else None)
        changed = 0

        while True:
            values = data.get("value", [])
            for item in values:
                graph_id = item.get("id")
                if not graph_id:
                    continue
                if "@removed" in item:
                    (
                        self.db.query(TodoListCache)
                        .filter(TodoListCache.user_oid == user_oid, TodoListCache.graph_list_id == graph_id)
                        .delete()
                    )
                    (
                        self.db.query(TodoTaskCache)
                        .filter(TodoTaskCache.user_oid == user_oid, TodoTaskCache.graph_list_id == graph_id)
                        .delete()
                    )
                    changed += 1
                    continue

                row = (
                    self.db.query(TodoListCache)
                    .filter(TodoListCache.user_oid == user_oid, TodoListCache.graph_list_id == graph_id)
                    .first()
                )
                if row:
                    row.display_name = item.get("displayName", row.display_name)
                    row.etag = item.get("@odata.etag")
                    row.is_owner = item.get("wellknownListName") is None
                else:
                    self.db.add(
                        TodoListCache(
                            user_oid=user_oid,
                            graph_list_id=graph_id,
                            display_name=item.get("displayName", "Unnamed"),
                            etag=item.get("@odata.etag"),
                            is_owner=item.get("wellknownListName") is None,
                            is_shared=False,
                        )
                    )
                changed += 1

            delta_link = data.get("@odata.deltaLink")
            next_link = data.get("@odata.nextLink")
            if delta_link:
                self._upsert_delta_state(user_oid, "lists", delta_link)
                break
            if next_link:
                data = self.graph.list_delta(user_oid, next_link)
                continue
            break

        self.db.commit()
        return changed

    def _sync_tasks_for_list(self, user_oid: str, list_id: str) -> int:
        state = self._get_delta_state(user_oid, "tasks", list_id)
        data = self.graph.task_delta(user_oid, list_id, state.delta_link if state else None)
        changed = 0
        existing_rows = (
            self.db.query(TodoTaskCache)
            .filter(TodoTaskCache.user_oid == user_oid, TodoTaskCache.graph_list_id == list_id)
            .all()
        )
        rows_by_task_id = {row.graph_task_id: row for row in existing_rows}

        while True:
            values = data.get("value", [])
            for item in values:
                task_id = item.get("id")
                if not task_id:
                    continue

                row = rows_by_task_id.get(task_id)
                if row and _is_local_only_task(row.raw_json):
                    # Local-only mode: ignore upstream updates/removals for locally managed tasks.
                    continue

                if "@removed" in item:
                    if row:
                        row.deleted = True
                        row.raw_json = json.dumps(item)
                    changed += 1
                    continue

                if not _is_after_import_cutoff(item):
                    if row:
                        self.db.delete(row)
                        rows_by_task_id.pop(task_id, None)
                    changed += 1
                    continue

                if not row:
                    row = TodoTaskCache(
                        user_oid=user_oid,
                        graph_list_id=list_id,
                        graph_task_id=task_id,
                        title=item.get("title", ""),
                        raw_json="{}",
                    )
                    self.db.add(row)
                    rows_by_task_id[task_id] = row

                if "title" in item and item.get("title") is not None:
                    row.title = item.get("title", row.title)
                if "body" in item:
                    body = item.get("body") or {}
                    row.body_content = body.get("content")
                if "importance" in item:
                    row.importance = item.get("importance")
                if "status" in item:
                    row.status = item.get("status")
                if "dueDateTime" in item:
                    due = item.get("dueDateTime") or {}
                    row.due_datetime = due.get("dateTime")
                    row.due_timezone = due.get("timeZone")
                if "recurrence" in item:
                    recurrence = item.get("recurrence")
                    row.recurrence_json = json.dumps(recurrence) if recurrence else None
                if "extensions" in item:
                    ext = extract_open_extension(item)
                    row.pool = ext.get("pool")
                    row.wf_status = ext.get("wfStatus")
                    row.trigger_ref = ext.get("triggerRef")
                # Auto-link imported tasks with due date/recurrence to built-in date trigger types.
                if (not row.trigger_ref) and row.due_datetime:
                    recurrence_type = None
                    if row.recurrence_json:
                        try:
                            recurrence = json.loads(row.recurrence_json)
                            recurrence_type = str((recurrence or {}).get("pattern", {}).get("type") or "").lower()
                        except Exception:
                            recurrence_type = None
                    if recurrence_type == "daily":
                        row.trigger_ref = "date:daily"
                    elif recurrence_type in {"weekly", "relativeweekly"}:
                        row.trigger_ref = "date:weekly"
                    elif recurrence_type in {"monthly", "absolutemonthly", "relativemonthly"}:
                        row.trigger_ref = "date:monthly"
                    elif recurrence_type in {"yearly", "absoluteyearly", "relativeyearly"}:
                        row.trigger_ref = "date:yearly"
                    else:
                        row.trigger_ref = "date"
                elif row.trigger_ref and row.trigger_ref.startswith("date") and not row.due_datetime:
                    row.trigger_ref = None
                row.raw_json = json.dumps(item)
                row.deleted = False
                changed += 1

            delta_link = data.get("@odata.deltaLink")
            next_link = data.get("@odata.nextLink")
            if delta_link:
                self._upsert_delta_state(user_oid, "tasks", delta_link, graph_list_id=list_id)
                break
            if next_link:
                data = self.graph.task_delta(user_oid, list_id, next_link)
                continue
            break

        self.db.commit()
        return changed
