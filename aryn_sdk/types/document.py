from typing import Annotated, Any, Literal, Optional, Union
from pydantic import AliasChoices, BaseModel, Field, JsonValue, PlainValidator, WrapSerializer


class DocumentMetadata(BaseModel):
    """ """

    account_id: str = Field(description="The account id containing the Document.")
    doc_id: str = Field(description="The unique id for the Document.")
    docset_id: str = Field(description="The unique id for the DocSet containing the Document.")
    created_at: str = Field(description="The time at which this document was added to the system.")
    name: str = Field(description="The name of this Document.")
    size: int = Field(description="The size of the Document in bytes.")
    content_type: str = Field(description="The content type of the source Document.")
    # TODO: What do we use properties for here?
    properties: Optional[dict] = Field(default=None, description="Additional properties for the Document.")


class Element(BaseModel):
    """ """

    id: str = Field(description="The unique id for the Element.")
    type: str = Field(description="The type of the Element.")
    text_representation: Optional[str] = Field(description="The text representation of the Element.")
    embedding: Optional[list[float]] = Field(description="The vector embedding of the Element.")
    properties: dict[str, Any] = Field(default={}, description="A map of properties for the Element.")
    bbox: tuple[float, float, float, float] = Field(description="The bounding box of the Element.")


class Document(BaseModel):
    """ """

    id: str = Field(description="The unique id for the Document.", validation_alias=AliasChoices("id", "doc_id"))
    elements: list[Element] = Field(default=[], description="The elements contained in the Document.")
    properties: dict[str, Any] = Field(default={}, description="A map of properties for the Document.")
    binary_data: Optional[str] = Field(
        default=None, description="The binary content of the document, encoded as a base64 string."
    )


class JSONPointer:
    """Represents a JSON Pointer as defined in RFC 6901.

    This is a standard way to reference a specific value in a JSON document.

    A JSON Pointer is a / delimited string, where each component is either an
    object key or an array index. When adding an element, you can also use '-'
    to indicate the end of an array. '~' and '/' must be escaped: ~ is encoded
    as ~0 and / is encoded as ~1.

    The easiest way to construct a JSONPointer instance is via JSONPointer.parse.

    Examples:
      - JSONPointer.parse("/foo/bar") -> JSONPointer(["foo", "bar"])
      - JSONPointer.parse("/foo/bar/3") -> JSONPointer(["foo", "bar", "3"])
    """

    parts: list[str]

    def __init__(self, parts: list[str]):
        self.parts = parts

    def __str__(self):
        return "/" + "/".join(p.replace("~", "~0").replace("/", "~1") for p in self.parts)

    @classmethod
    def parse(cls, value: Union[str, list[str], "JSONPointer"]) -> "JSONPointer":
        """Creates a JSONPointer from a string.

        Also handles a list o strings (like the constructor), and a
        JSONPointer instance, which is returned as-is. This is for Pydantic
        compatibility.
        """
        if isinstance(value, JSONPointer):
            return value
        elif isinstance(value, list):
            return cls(value)

        assert isinstance(value, str)

        if value == "":
            return cls([])

        if not value.startswith("/"):
            raise ValueError("JSON Pointer must start with a '/'")

        value = value[1:]
        parts = [] if len(value) == 0 else value.split("/")

        try:
            dash_idx = parts.index("-")
        except ValueError:
            dash_idx = -1

        if dash_idx != -1 and dash_idx != len(parts) - 1:
            raise ValueError("Array end marker '-' must be at the end of the path.")

        return cls([p.replace("~1", "/").replace("~0", "~") for p in parts])


# This is a type that can be used in a Pydantic model that will be used to convert to/from
# JSONPointer strings.
JSONPointerType = Annotated[
    JSONPointer,
    PlainValidator(JSONPointer.parse),
    WrapSerializer(lambda v, handler: str(v) if isinstance(v, JSONPointer) else handler(v)),
]


class JSONPatchOperationBase(BaseModel):
    """Base class to represent a JSON Patch operation.

    JSONPatch is a mechanism for representing updates to a JSON document
    defined at https://jsonpatch.com.
    """

    pass


class AddOperation(JSONPatchOperationBase):
    op: Literal["add"] = "add"
    path: JSONPointerType
    value: JsonValue


class RemoveOperation(JSONPatchOperationBase):
    op: Literal["remove"] = "remove"
    path: JSONPointerType


class ReplaceOperation(JSONPatchOperationBase):
    op: Literal["replace"] = Field(
        default="replace", description="The type of JSON Patch operation. Currently only 'replace' is supported"
    )
    path: JSONPointerType = Field(
        description="a [JSON Pointer](https://datatracker.ietf.org/doc/html/rfc6901) object identifying the value to be replaced."
    )
    value: JsonValue = Field(description="The new value to replace the existing value.")


class FieldUpdates(BaseModel):
    operations: list[ReplaceOperation] = Field(
        description="A list of updates to a document that will be applied sequentially."
    )
