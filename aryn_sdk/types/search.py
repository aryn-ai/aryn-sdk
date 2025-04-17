from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class SearchRequest(BaseModel):
    query: Annotated[Optional[str], Field(description="The query to search for")] = None
    query_type: Annotated[
        Literal["keyword", "lexical", "vector", "hybrid"], Field(description="The type of query to perform.")
    ] = "lexical"
    properties_filter: Annotated[
        Optional[str], Field(description="A filter to apply to the properties of the documents.")
    ] = None
    return_type: Annotated[Literal["doc", "element"], Field(description="The type of result to return.")] = "doc"
    include_fields: Annotated[
        Optional[list[str]],
        Field(
            description="When specified, the server performs a projection to return only the fields specified by this list of JsonPaths (see RFC 9535) given as a list of strings.",
        ),
    ] = None
    debug_info: Annotated[
        Optional[bool],
        Field(
            description="When `True`, the server returns additional debug information (the embedding calculated for a vector or hybrid query) in the response.",
        ),
    ] = False
    include_element_embedding: Annotated[
        Optional[bool],
        Field(
            description='When `False`, and return_type is "element", the server does not return the embeddings of elements in the response.',
        ),
    ] = False

    @model_validator(mode="after")
    def check_query_or_properties_filter_present(self):
        if self.query is None and self.properties_filter is None:
            raise ValueError("Either query or properties_filter must be provided")
        return self

    @model_validator(mode="after")
    def require_query_when_query_type_uses_vector_search(self):
        if self.query is None and self.query_type in ("vector", "hybrid"):
            raise ValueError("query must be provided when query_type is vector or hybrid")
        return self

    @model_validator(mode="after")
    def disallow_empty_string_when_query_set(self):
        if self.query == "":
            raise ValueError("query may be omitted, but must not be an empty string")
        return self

    class Config:
        # Ensure that extra fields are not allowed
        extra = "forbid"


class SearchResponse(BaseModel):
    results: Annotated[
        list,
        Field(
            description="The list of results returned by the query. These are Json objects representing the documents or elements that matched the query, possibly filtered by the optional projection specified by include_fields."
        ),
    ]

    # the field query_embedding below is to allow users to debug their queries and/or their docset, and is only present
    # when query_type is vector or hybrid and debug_info is True
    query_embedding: Annotated[
        Optional[list[float]],
        Field(
            description="The embedding calculated for the query, if the query type is vector or hybrid and `debug_info` is True.",
        ),
    ] = None

    next_page_token: Annotated[
        Optional[str],
        Field(
            description="Reserved for future use. Will be a pagination token that can be used to retrieve the next page of results.",
        ),
    ] = None
