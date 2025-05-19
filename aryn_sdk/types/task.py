from enum import Enum

from typing import Annotated, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"

    @classmethod
    def _missing_(cls, value):
        value = value.lower()  # type: ignore
        for member in cls:
            if member.value == value:
                return member
        return None


class AsyncTaskMetadata(BaseModel):
    """Metadata associated with an async task."""

    action: Annotated[str, Field(description="The path of the endpoint used to invoke the task.")]
    task_status: Annotated[TaskStatus, Field(description="The current status of the task.")]
    userdata: Annotated[Optional[str], Field(description="Additional metadata associated with the task.")] = None


class AsyncTaskMap(BaseModel):
    """Metadata describing a list of async tasks."""

    tasks: Annotated[dict[str, AsyncTaskMetadata], Field(description="A map of task ids to metadata for async tasks.")]
