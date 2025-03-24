from enum import StrEnum

from typing import Optional
from pydantic import BaseModel


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class AsyncTaskMetadata(BaseModel):
    action: str
    task_status: TaskStatus
    userdata: Optional[str] = None


class AyncTaskList(BaseModel):
    tasks: list[AsyncTaskMetadata]
