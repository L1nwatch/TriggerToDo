#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "triggertodo.db"


def table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    row = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    backup = DB_PATH.with_name(f"{DB_PATH.name}.bak_mig_user_oid")
    backup.write_bytes(DB_PATH.read_bytes())
    print(f"[migrate] backup created: {backup}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=OFF")
    cur.execute("BEGIN")
    try:
        for name in [
            "todo_list_cache",
            "todo_task_cache",
            "delta_state",
            "trigger_rule",
            "trigger_event",
            "trigger_epic",
            "jira_issue_override",
            "user_token_cache",
        ]:
            if table_exists(cur, name):
                cur.execute(f"ALTER TABLE {name} RENAME TO {name}_old")

        cur.executescript(
            """
            CREATE TABLE todo_list_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_list_id VARCHAR(128) NOT NULL,
                display_name VARCHAR(512) NOT NULL,
                is_owner BOOLEAN NOT NULL DEFAULT 1,
                is_shared BOOLEAN NOT NULL DEFAULT 0,
                etag VARCHAR(256),
                updated_at DATETIME
            );
            CREATE UNIQUE INDEX ix_todo_list_graph_unique_v2 ON todo_list_cache (graph_list_id);
            CREATE INDEX ix_todo_list_graph_list_id_v2 ON todo_list_cache (graph_list_id);

            CREATE TABLE todo_task_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_list_id VARCHAR(128) NOT NULL,
                graph_task_id VARCHAR(128) NOT NULL,
                title VARCHAR(1024) NOT NULL,
                body_content TEXT,
                importance VARCHAR(32),
                status VARCHAR(64),
                due_datetime VARCHAR(64),
                due_timezone VARCHAR(64),
                recurrence_json TEXT,
                pool VARCHAR(128),
                wf_status VARCHAR(128),
                trigger_ref VARCHAR(128),
                raw_json TEXT NOT NULL,
                deleted BOOLEAN NOT NULL DEFAULT 0,
                updated_at DATETIME
            );
            CREATE UNIQUE INDEX ix_task_list_task_v2 ON todo_task_cache (graph_list_id, graph_task_id);
            CREATE INDEX ix_todo_task_graph_list_id_v2 ON todo_task_cache (graph_list_id);
            CREATE INDEX ix_todo_task_graph_task_id_v2 ON todo_task_cache (graph_task_id);
            CREATE INDEX ix_todo_task_pool_v2 ON todo_task_cache (pool);
            CREATE INDEX ix_todo_task_wf_status_v2 ON todo_task_cache (wf_status);
            CREATE INDEX ix_todo_task_trigger_ref_v2 ON todo_task_cache (trigger_ref);
            CREATE INDEX ix_todo_task_deleted_v2 ON todo_task_cache (deleted);

            CREATE TABLE delta_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_list_id VARCHAR(128),
                resource_type VARCHAR(32) NOT NULL,
                delta_link TEXT,
                updated_at DATETIME
            );
            CREATE UNIQUE INDEX ix_delta_state_unique_v2 ON delta_state (graph_list_id, resource_type);
            CREATE INDEX ix_delta_state_graph_list_id_v2 ON delta_state (graph_list_id);
            CREATE INDEX ix_delta_state_resource_type_v2 ON delta_state (resource_type);

            CREATE TABLE trigger_rule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(256) NOT NULL,
                source_pool VARCHAR(128),
                source_wf_status VARCHAR(128),
                target_pool VARCHAR(128),
                target_wf_status VARCHAR(128),
                enabled BOOLEAN NOT NULL DEFAULT 1,
                cron_expression VARCHAR(128),
                updated_at DATETIME
            );
            CREATE INDEX ix_trigger_rule_enabled_v2 ON trigger_rule (enabled);

            CREATE TABLE trigger_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(256) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 0,
                occurred_at DATETIME,
                updated_at DATETIME
            );
            CREATE INDEX ix_trigger_event_is_active_v2 ON trigger_event (is_active);

            CREATE TABLE trigger_epic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epic_key VARCHAR(64) NOT NULL,
                name VARCHAR(512) NOT NULL,
                status VARCHAR(128),
                priority VARCHAR(64),
                updated_at DATETIME
            );
            CREATE UNIQUE INDEX ix_trigger_epic_key_unique_v2 ON trigger_epic (epic_key);
            CREATE INDEX ix_trigger_epic_epic_key_v2 ON trigger_epic (epic_key);

            CREATE TABLE jira_issue_override (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_key VARCHAR(64) NOT NULL,
                summary VARCHAR(2048),
                updated_at DATETIME
            );
            CREATE UNIQUE INDEX ix_jira_override_issue_unique_v2 ON jira_issue_override (issue_key);
            CREATE INDEX ix_jira_issue_override_issue_key_v2 ON jira_issue_override (issue_key);

            CREATE TABLE user_token_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key VARCHAR(128) NOT NULL UNIQUE,
                encrypted_cache_blob TEXT NOT NULL,
                updated_at DATETIME
            );
            CREATE INDEX ix_user_token_cache_user_key_v2 ON user_token_cache (user_key);
            """
        )

        if table_exists(cur, "todo_list_cache_old"):
            cur.execute(
                """
                INSERT OR REPLACE INTO todo_list_cache
                (graph_list_id, display_name, is_owner, is_shared, etag, updated_at)
                SELECT graph_list_id, display_name, is_owner, is_shared, etag, updated_at
                FROM todo_list_cache_old
                """
            )
        if table_exists(cur, "todo_task_cache_old"):
            cur.execute(
                """
                INSERT OR REPLACE INTO todo_task_cache
                (graph_list_id, graph_task_id, title, body_content, importance, status, due_datetime, due_timezone,
                 recurrence_json, pool, wf_status, trigger_ref, raw_json, deleted, updated_at)
                SELECT graph_list_id, graph_task_id, title, body_content, importance, status, due_datetime, due_timezone,
                       recurrence_json, pool, wf_status, trigger_ref, raw_json, deleted, updated_at
                FROM todo_task_cache_old
                """
            )
        if table_exists(cur, "delta_state_old"):
            cur.execute(
                """
                INSERT OR REPLACE INTO delta_state (graph_list_id, resource_type, delta_link, updated_at)
                SELECT graph_list_id, resource_type, delta_link, updated_at
                FROM delta_state_old
                """
            )
        if table_exists(cur, "trigger_rule_old"):
            cur.execute(
                """
                INSERT INTO trigger_rule
                (name, source_pool, source_wf_status, target_pool, target_wf_status, enabled, cron_expression, updated_at)
                SELECT name, source_pool, source_wf_status, target_pool, target_wf_status, enabled, cron_expression, updated_at
                FROM trigger_rule_old
                """
            )
        if table_exists(cur, "trigger_event_old"):
            cur.execute(
                """
                INSERT INTO trigger_event (name, is_active, occurred_at, updated_at)
                SELECT name, is_active, occurred_at, updated_at
                FROM trigger_event_old
                """
            )
        if table_exists(cur, "trigger_epic_old"):
            cur.execute(
                """
                INSERT OR REPLACE INTO trigger_epic (epic_key, name, status, priority, updated_at)
                SELECT epic_key, name, status, priority, updated_at
                FROM trigger_epic_old
                """
            )
        if table_exists(cur, "jira_issue_override_old"):
            cur.execute(
                """
                INSERT OR REPLACE INTO jira_issue_override (issue_key, summary, updated_at)
                SELECT issue_key, summary, updated_at
                FROM jira_issue_override_old
                """
            )

        for name in [
            "todo_list_cache_old",
            "todo_task_cache_old",
            "delta_state_old",
            "trigger_rule_old",
            "trigger_event_old",
            "trigger_epic_old",
            "jira_issue_override_old",
            "user_token_cache_old",
        ]:
            if table_exists(cur, name):
                cur.execute(f"DROP TABLE {name}")

        conn.commit()
        print("[migrate] completed")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[migrate] ERROR: {exc}", file=sys.stderr)
        raise
