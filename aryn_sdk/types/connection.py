from abc import ABC
from datetime import datetime
from enum import Enum

from typing import Annotated, Literal, Optional, TypeAlias

from pydantic import BaseModel, Field


class ConnectionType(str, Enum):
    DATABRICKS = "databricks"
    S3 = "s3"


class ConnectionBase(BaseModel, ABC):
    name: Optional[str] = None
    account_id: Optional[str] = None
    connection_id: Optional[str] = None
    created_at: Optional[datetime] = None


class S3Connection(ConnectionBase):
    type: Literal[ConnectionType.S3] = ConnectionType.S3
    bucket: str
    role_arn: str
    external_id: Optional[str] = None


class DataBricksUnityCatalogConnection(ConnectionBase):
    type: Literal[ConnectionType.DATABRICKS] = ConnectionType.DATABRICKS
    workspace_url: str
    catalog: str
    token: str


Connection: TypeAlias = Annotated[
    (S3Connection | DataBricksUnityCatalogConnection),
    Field(discriminator="type"),
]
