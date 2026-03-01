from typing import Any, Optional

from pydantic import BaseModel, Field


class GraphListCreate(BaseModel):
    displayName: str


class GraphListUpdate(BaseModel):
    displayName: str


class OpenExtensionFields(BaseModel):
    pool: Optional[str] = None
    wfStatus: Optional[str] = None
    triggerRef: Optional[str] = None
    source: Optional[str] = None
    epicKey: Optional[str] = None


class RecurrencePayload(BaseModel):
    pattern: dict[str, Any]
    range: dict[str, Any]


class GraphTaskCreate(BaseModel):
    title: str
    body: Optional[dict[str, Any]] = None
    dueDateTime: Optional[dict[str, str]] = None
    importance: Optional[str] = None
    recurrence: Optional[RecurrencePayload] = None
    extensions: OpenExtensionFields = Field(default_factory=OpenExtensionFields)


class GraphTaskUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[dict[str, Any]] = None
    dueDateTime: Optional[dict[str, str]] = None
    importance: Optional[str] = None
    status: Optional[str] = None
    recurrence: Optional[RecurrencePayload] = None
    extensions: Optional[OpenExtensionFields] = None


class TriggerRuleCreate(BaseModel):
    name: str
    source_pool: Optional[str] = None
    source_wf_status: Optional[str] = None
    target_pool: Optional[str] = None
    target_wf_status: Optional[str] = None
    enabled: bool = True
    cron_expression: Optional[str] = None


class TriggerRuleUpdate(BaseModel):
    name: Optional[str] = None
    source_pool: Optional[str] = None
    source_wf_status: Optional[str] = None
    target_pool: Optional[str] = None
    target_wf_status: Optional[str] = None
    enabled: Optional[bool] = None
    cron_expression: Optional[str] = None


class JiraIssueUpdate(BaseModel):
    summary: Optional[str] = None


class TriggerEventCreate(BaseModel):
    name: str


class TriggerEventUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class TriggerEpicCreate(BaseModel):
    epic_key: str
    name: str
    status: Optional[str] = None
    priority: Optional[str] = None


class TriggerEpicUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
