import json
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.graph import OPEN_EXTENSION_NAME
from app.models import TodoTaskCache, TriggerRule


class TriggerEngine:
    def __init__(self, interval_seconds: int):
        self.interval_seconds = interval_seconds
        self.scheduler = BackgroundScheduler()
        self._started = False

    def start(self):
        if self._started:
            return
        self.scheduler.add_job(self.run_once_all_users, "interval", seconds=self.interval_seconds, id="trigger_scan")
        self.scheduler.start()
        self._started = True

    def shutdown(self):
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def run_once_all_users(self):
        db = SessionLocal()
        try:
            self.run_once_for_user(db)
        finally:
            db.close()

    def run_once_for_user(self, db: Session) -> dict[str, Any]:
        moved = 0
        rules = (
            db.query(TriggerRule)
            .filter(TriggerRule.enabled.is_(True))
            .all()
        )

        for rule in rules:
            query = db.query(TodoTaskCache).filter(TodoTaskCache.deleted.is_(False))
            if rule.source_pool is not None:
                query = query.filter(TodoTaskCache.pool == rule.source_pool)
            if rule.source_wf_status is not None:
                query = query.filter(TodoTaskCache.wf_status == rule.source_wf_status)

            for task in query.all():
                ext_fields = {
                    "pool": rule.target_pool if rule.target_pool is not None else task.pool,
                    "wfStatus": rule.target_wf_status if rule.target_wf_status is not None else task.wf_status,
                    "triggerRef": str(rule.id),
                }

                raw_task = json.loads(task.raw_json)
                extensions = raw_task.get("extensions") or []
                found = False
                for ext in extensions:
                    if ext.get("extensionName") == OPEN_EXTENSION_NAME:
                        ext["pool"] = ext_fields["pool"]
                        ext["wfStatus"] = ext_fields["wfStatus"]
                        ext["triggerRef"] = ext_fields["triggerRef"]
                        found = True
                        break
                if not found:
                    extensions.append(
                        {
                            "extensionName": OPEN_EXTENSION_NAME,
                            "pool": ext_fields["pool"],
                            "wfStatus": ext_fields["wfStatus"],
                            "triggerRef": ext_fields["triggerRef"],
                            "source": "triggertodo",
                        }
                    )
                raw_task["extensions"] = extensions
                task.raw_json = json.dumps(raw_task)

                task.pool = ext_fields["pool"]
                task.wf_status = ext_fields["wfStatus"]
                task.trigger_ref = ext_fields["triggerRef"]
                moved += 1

        db.commit()
        return {"moved": moved}
