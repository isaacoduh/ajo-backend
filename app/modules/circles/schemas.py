"""Circles API schemas."""

from pydantic import BaseModel


class PingResponse(BaseModel):
    module: str
    status: str

