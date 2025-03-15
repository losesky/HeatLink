from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    slug: str
    parent_id: Optional[int] = None
    icon: Optional[str] = None
    order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    slug: Optional[str] = None
    parent_id: Optional[int] = None
    icon: Optional[str] = None
    order: Optional[int] = None


class CategoryInDB(CategoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Category(CategoryInDB):
    pass


class CategoryWithChildren(Category):
    children: List['CategoryWithChildren'] = []


# Resolve forward reference
CategoryWithChildren.model_rebuild()


class CategoryTree(BaseModel):
    categories: List[CategoryWithChildren] 