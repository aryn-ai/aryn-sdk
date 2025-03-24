from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, JsonValue

from .prompt import PromptType
from .schema import Schema


class DocSetMetadata(BaseModel):
    account_id: str = Field(description="The account id containing the DocSet.")
    docset_id: str = Field(description="The unique id for the DocSet.")
    name: str = Field(description="The name of the DocSet.")
    created_at: datetime = Field(description="The creation time of this DocSet.")
    readonly: bool = Field(description="Whether the DocSet is read-only.")
    properties: Optional[dict[str, JsonValue]] = Field(
        default=None, description="Additional properties for the DocSet."
    )
    size: Optional[int] = Field(default=None, description="The size of the DocSet in bytes.")
    query_schema: Optional[Schema] = Field(default=None, description="The schema of the DocSet.")
    # Map from prompt type to prompt_id.
    prompts: dict[PromptType, str] = Field(default={}, description="The prompts associated with this DocSet.")


class DocSetUpdate(BaseModel):
    name: Optional[str] = None
    properties: Optional[dict[str, JsonValue]] = None
    query_schema: Optional[Schema] = None
    prompts: Optional[dict[PromptType, str]] = None
