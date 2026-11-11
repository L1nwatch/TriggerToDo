"""Input and output schemas shared by TriggerToDo and the FengDock MCP tools."""

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator


def _require_iso_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Use YYYY-MM-DD for dates")
    return value


ScrumDate = Annotated[date, BeforeValidator(_require_iso_date)]
ScrumId = Annotated[int, Field(strict=True, ge=1, le=2**63 - 1)]
ScrumName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
TaskRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)]
StoryPoints = Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]
SprintStatus = Literal["draft", "active", "completed"]
ItemStatus = Literal["todo", "doing", "done"]
TaskPriority = Literal["low", "normal", "high"]


class ScrumInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScrumChanges(ScrumInput):
    name: ScrumName | None = None
    goal: str | None = Field(default=None, description="Pass null to clear the goal")
    start_date: ScrumDate | None = Field(default=None, description="Pass null to clear the start date")
    end_date: ScrumDate | None = Field(default=None, description="Pass null to clear the end date")
    status: SprintStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Specify at least one Sprint field to update")
        for field in self.model_fields_set & {"name", "status"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AddScrumItem(ScrumInput):
    action: Literal["add"]
    list_id: TaskRef = Field(description="listId returned by search_todos")
    task_id: TaskRef = Field(description="taskId returned by search_todos")
    points: StoryPoints = 0
    status: ItemStatus | None = Field(default=None, description="Defaults to the linked task's current status")


class CreateScrumItem(ScrumInput):
    action: Literal["create"]
    list_id: TaskRef | None = Field(default=None, description="Existing task list ID. Defaults to Inbox")
    title: TaskTitle
    description: str | None = None
    priority: TaskPriority = "normal"
    points: StoryPoints = 0
    status: ItemStatus = "todo"


class UpdateScrumItem(ScrumInput):
    action: Literal["update"]
    item_id: ScrumId = Field(description="Sprint item ID from list_scrums or a write result")
    title: TaskTitle | None = None
    description: str | None = Field(default=None, description="Pass null to clear the task description")
    priority: TaskPriority | None = None
    points: StoryPoints | None = None
    status: ItemStatus | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        fields = self.model_fields_set - {"action", "item_id"}
        if not fields:
            raise ValueError("Specify at least one item field to update")
        for field in fields - {"description"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class RemoveScrumItem(ScrumInput):
    action: Literal["remove"]
    item_id: ScrumId = Field(description="Sprint item ID to unlink from this Sprint")


class MoveScrumItem(ScrumInput):
    action: Literal["move"]
    item_id: ScrumId = Field(description="ID of a todo or doing item in the source Sprint")


ScrumItemOperation = Annotated[
    AddScrumItem | CreateScrumItem | UpdateScrumItem | RemoveScrumItem | MoveScrumItem,
    Field(discriminator="action"),
]
ScrumOperations = Annotated[
    list[ScrumItemOperation],
    Field(min_length=1, max_length=100, description="Apply these operations in order in one transaction"),
]


class ScrumItemBatch(ScrumInput):
    operations: ScrumOperations
    destination_scrum_id: ScrumId | None = Field(default=None, description="Next Sprint ID for move operations")

    @model_validator(mode="after")
    def validate_destination(self):
        has_moves = any(isinstance(operation, MoveScrumItem) for operation in self.operations)
        if has_moves != (self.destination_scrum_id is not None):
            raise ValueError("Provide destination_scrum_id exactly when the batch contains a move")
        return self


class ScrumTask(BaseModel):
    list_id: str
    task_id: str
    title: str
    description: str | None
    status: str | None
    wf_status: str | None
    importance: str | None
    due_datetime: str | None
    trigger_ref: str | None
    epic_key: str | None
    source: str


class ScrumItem(BaseModel):
    id: int
    list_id: str
    task_id: str
    points: int
    status: ItemStatus
    added_after_start: bool
    updated_at: datetime
    task: ScrumTask | None


class ScrumSummary(BaseModel):
    items: int
    points: int
    done_points: int
    points_by_status: dict[ItemStatus, int]
    count_by_status: dict[ItemStatus, int]
    added_after_start: int


class ScrumState(BaseModel):
    id: int
    name: str
    goal: str | None
    start_date: str | None
    end_date: str | None
    target_points: int
    status: SprintStatus
    completed_at: datetime | None
    updated_at: datetime
    summary: ScrumSummary
    items: list[ScrumItem]


class ScrumItemOperationResult(BaseModel):
    action: Literal["add", "create", "update", "remove", "move"]
    item_id: int
    list_id: str
    task_id: str


class ScrumItemBatchResult(BaseModel):
    scrum: ScrumState
    destination_scrum: ScrumState | None
    results: list[ScrumItemOperationResult]
