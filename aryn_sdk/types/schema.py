from typing import Any, Optional
from pydantic import BaseModel, Field

# TODO: Some kind of TypeAlias to get this to work with Sycamore schemas as well. Uggh.


class SchemaField(BaseModel):
    """Represents a field in a DocSet schema."""

    name: str = Field(description="The name of the field.")
    field_type: str = Field(description="The type of the field.")
    default: Optional[Any] = Field(default=None, description="The default value for the field.")
    description: Optional[str] = Field(default=None, description="A natural language description of the field.")
    examples: Optional[list[Any]] = Field(default=None, description="A list of example values for the field.")


class Schema(BaseModel):
    """Represents the schema of a DocSet."""

    fields: list[SchemaField] = Field(description="A list of fields belong to this schema.")
