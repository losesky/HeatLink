from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TagBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None


class TagInDB(TagBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Tag(TagInDB):
    pass 