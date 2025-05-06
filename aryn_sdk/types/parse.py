from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator


class TokenizerOptions(BaseModel):
    model_name: Annotated[Optional[str], Field(description="The name of the tokenizer model.")] = None
    max_tokens: Annotated[Optional[int], Field(description="The maximum number of tokens.")] = None

    class Config:
        # Ensure that extra fields are not allowed
        extra = "forbid"


class ChunkingOptions(BaseModel):
    strategy: Annotated[
        Optional[Union[Literal["maximize_within_limit"], Literal["mixed_multi_column"], Literal["context_rich"]]],
        Field(
            description="The strategy to use for chunking. For convenience, when chunking options is specified but its strategy is unspecified, the service uses its default strategy."
        ),
    ] = None
    max_tokens: Annotated[Optional[int], Field(description="The maximum number of tokens per chunk.")] = None
    tokenizer: Annotated[
        Optional[Union[Literal["openai_tokenizer"], Literal["character_tokenizer"], Literal["huggingface_tokenizer"]]],
        Field(description="The tokenizer to use for chunking."),
    ] = None
    tokenizer_options: Annotated[Optional[TokenizerOptions], Field(description="Options for the tokenizer.")] = None
    merge_across_pages: Annotated[Optional[bool], Field(description="Whether to merge across pages.")] = None

    @model_validator(mode="after")
    def check_max_tokens_is_reasonable(self):
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("When specified, max tokens must be at least 1.")
        return self

    @model_validator(mode="after")
    def check_merge_across_pages_applies(self):
        if self.merge_across_pages is not None and self.strategy == "mixed_multi_column":
            raise ValueError("Merge across pages option is not supported for mixed_multi_column strategy.")
        return self

    @model_validator(mode="after")
    def check_tokenizer_options_applies(self):
        if self.tokenizer == "character_tokenizer" and self.tokenizer_options is not None:
            raise ValueError("character_tokenizer takes no tokenizer_options.")

    class Config:
        # Ensure that extra fields are not allowed
        extra = "forbid"
