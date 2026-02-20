# ruff: noqa: F401
from typing import Any, Optional
from pydantic import AliasChoices, BaseModel, Field

# If present, import the local datatype module; otherwise, import from sycamore.datatype
try:
    from ._datatype import DataType
except ImportError:
    from sycamore.datatype import DataType

# If present, import the local schema module; otherwise, import from sycamore.schema
try:
    from ._schema import (
        SchemaV2 as Schema,
        make_named_property,
        make_property,
        NamedProperty,
        ObjectProperty,
        ArrayProperty,
        PropertyType,
        StringProperty,
    )
except ImportError:
    from sycamore.schema import (
        SchemaV2 as Schema,
        make_named_property,
        make_property,
        NamedProperty,
        ObjectProperty,
        ArrayProperty,
        PropertyType,
        StringProperty,
    )


class SchemaPropertyNames(BaseModel):
    """Represents the names of properties belonging to a DocSet schema."""

    names: list[str] = Field(description="A list of names of properties that belong to a schema.")
