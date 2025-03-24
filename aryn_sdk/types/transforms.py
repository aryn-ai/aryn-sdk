from pydantic import BaseModel


class TransformResponse(BaseModel):
    exit_status: int
