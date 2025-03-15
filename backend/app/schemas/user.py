from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    username: str
    is_active: bool = True
    is_superuser: bool = False


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class UserInDB(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime
    hashed_password: str

    class Config:
        from_attributes = True


class User(BaseModel):
    id: int
    email: EmailStr
    username: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubscriptionBase(BaseModel):
    type: str  # "source", "category", "tag"
    target_id: str


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionInDB(SubscriptionBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class Subscription(SubscriptionInDB):
    pass


class UserWithSubscriptions(User):
    subscriptions: List[Subscription] = [] 