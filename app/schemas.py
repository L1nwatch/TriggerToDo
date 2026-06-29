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
    epic_key: Optional[str] = None
    name: str
    status: Optional[str] = None
    priority: Optional[str] = None


class TriggerEpicUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


class TriggerMilestoneCreate(BaseModel):
    title: str
    milestone_at: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    epic_keys: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    scrum_ids: list[str] = Field(default_factory=list)


class TriggerMilestoneUpdate(BaseModel):
    title: Optional[str] = None
    milestone_at: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    epic_keys: Optional[list[str]] = None
    task_ids: Optional[list[str]] = None
    scrum_ids: Optional[list[str]] = None


class TriggerScrumItemCreate(BaseModel):
    list_id: str
    task_id: str
    points: int = 0
    status: str = "todo"


class TriggerScrumCreate(BaseModel):
    name: str
    goal: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    target_points: int = 0
    status: str = "draft"
    items: list[TriggerScrumItemCreate] = Field(default_factory=list)


class TriggerScrumUpdate(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    target_points: Optional[int] = None
    status: Optional[str] = None
    items: Optional[list[TriggerScrumItemCreate]] = None


class TriggerScrumItemStatusUpdate(BaseModel):
    status: str


class TriggerRoutineCheckUpdate(BaseModel):
    list_id: str
    task_id: str
    check_date: str
    checked: bool = True
