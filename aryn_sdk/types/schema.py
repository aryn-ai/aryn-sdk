from typing import Any, Optional
from pydantic import AliasChoices, BaseModel, Field

# TODO: Some kind of TypeAlias to get this to work with Sycamore schemas as well. Uggh.


class SchemaProperty(BaseModel):
    """Represents a field in a DocSet schema."""

    name: str = Field(description="The name of the property.")
    property_type: str = Field(
        description="The type of the field.", validation_alias=AliasChoices("field_type", "property_type")
    )

    @property
    def field_type(self) -> str:
        """Alias for property_type."""
        return self.property_type

    default: Optional[Any] = Field(default=None, description="The default value for the property.")
    description: Optional[str] = Field(default=None, description="A natural language description of the property.")
    examples: Optional[list[Any]] = Field(default=None, description="A list of example values for the property.")


SchemaField = SchemaProperty


class Schema(BaseModel):
    """Represents the schema of a DocSet."""

    properties: list[SchemaProperty] = Field(
        description="A list of properties belong to this schema.",
        validation_alias=AliasChoices("properties", "fields"),
    )

    @property
    def fields(self) -> list[SchemaProperty]:
        """Alias for properties."""
        return self.properties


class SchemaPropertyNames(BaseModel):
    """Represents the names of properties belonging to a DocSet schema."""

    names: list[str] = Field(description="A list of names of properties that belong to a schema.")
