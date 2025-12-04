from abc import ABC
from datetime import datetime
from enum import Enum

from typing import Annotated, Literal, Optional, TypeAlias

from pydantic import BaseModel, Field


class ConnectionType(str, Enum):
    DATABRICKS = "databricks"
    S3 = "s3"
    S3_TABLES = "s3tables"


class ConnectionBase(BaseModel, ABC):
    name: Optional[str] = None
    account_id: Optional[str] = None
    connection_id: Optional[str] = None
    created_at: Optional[datetime] = None


class AWSConnection(ConnectionBase):
    role_arn: str
    external_id: Optional[str] = None
    region: str = "us-east-1"


class S3Connection(AWSConnection):
    type: Literal[ConnectionType.S3] = ConnectionType.S3
    bucket: str


class S3TablesConnection(AWSConnection):
    type: Literal[ConnectionType.S3_TABLES] = ConnectionType.S3_TABLES
    aws_account_id: str
    bucket: str


class DataBricksUnityCatalogConnection(ConnectionBase):
    type: Literal[ConnectionType.DATABRICKS] = ConnectionType.DATABRICKS
    workspace_url: str
    catalog: str
    token: str


Connection: TypeAlias = Annotated[
    (S3Connection | DataBricksUnityCatalogConnection | S3TablesConnection),
    Field(discriminator="type"),
]
