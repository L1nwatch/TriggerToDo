from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserTokenCache(Base):
    __tablename__ = "user_token_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, default="default-owner")
    encrypted_cache_blob: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class TodoListCache(Base):
    __tablename__ = "todo_list_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    graph_list_id: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(512))
    is_owner: Mapped[bool] = mapped_column(Boolean, default=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_todo_list_graph_unique", "graph_list_id", unique=True),)


class TodoTaskCache(Base):
    __tablename__ = "todo_task_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    graph_list_id: Mapped[str] = mapped_column(String(128), index=True)
    graph_task_id: Mapped[str] = mapped_column(String(128), index=True)

    title: Mapped[str] = mapped_column(String(1024))
    body_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    due_datetime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    due_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    recurrence_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    pool: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    wf_status: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    trigger_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    raw_json: Mapped[str] = mapped_column(Text)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_task_list_task", "graph_list_id", "graph_task_id", unique=True),)


class DeltaState(Base):
    __tablename__ = "delta_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    graph_list_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), index=True)
    delta_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_delta_state_unique", "graph_list_id", "resource_type", unique=True),)


class TriggerRule(Base):
    __tablename__ = "trigger_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256))

    source_pool: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_wf_status: Mapped[str | None] = mapped_column(String(128), nullable=True)

    target_pool: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_wf_status: Mapped[str | None] = mapped_column(String(128), nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    cron_expression: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class TriggerEvent(Base):
    __tablename__ = "trigger_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class TriggerEpic(Base):
    __tablename__ = "trigger_epic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    epic_key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_trigger_epic_key_unique", "epic_key", unique=True),)


class JiraIssueOverride(Base):
    __tablename__ = "jira_issue_override"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_key: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_jira_override_issue_unique", "issue_key", unique=True),)
