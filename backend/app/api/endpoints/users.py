from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Body
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user, get_current_superuser
from app.core.security import get_password_hash
from app.crud.user import (
    get_user, get_users, create_user, update_user, delete_user,
    get_user_with_subscriptions, add_favorite, remove_favorite, get_favorites,
    get_read_history, create_subscription, delete_subscription, get_subscriptions
)
from app.models.user import User
from app.schemas.user import (
    User as UserSchema, UserCreate, UserUpdate, UserWithSubscriptions,
    Subscription, SubscriptionCreate
)
from app.schemas.news import NewsListItem

router = APIRouter()


@router.get("/", response_model=List[UserSchema])
def read_users(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Retrieve users.
    """
    users = get_users(
        db,
        skip=skip,
        limit=limit,
        active_only=active_only
    )
    return users


@router.post("/", response_model=UserSchema)
def create_new_user(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Create new user.
    """
    hashed_password = get_password_hash(user_in.password)
    user = create_user(db, user_in, hashed_password)
    return user


@router.get("/me", response_model=UserSchema)
def read_user_me(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    return current_user


@router.put("/me", response_model=UserSchema)
def update_user_me(
    *,
    db: Session = Depends(get_db),
    password: Optional[str] = Body(None),
    email: Optional[str] = Body(None),
    username: Optional[str] = Body(None),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update own user.
    """
    current_user_data = UserUpdate(
        email=email,
        username=username,
        password=password
    )
    
    if password:
        hashed_password = get_password_hash(password)
    else:
        hashed_password = None
    
    user = update_user(
        db, user_id=current_user.id, user=current_user_data, hashed_password=hashed_password
    )
    return user


@router.get("/me/subscriptions", response_model=UserWithSubscriptions)
def read_user_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user subscriptions.
    """
    result = get_user_with_subscriptions(db, user_id=current_user.id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    
    user = result["user"]
    subscriptions = result["subscriptions"]
    
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "subscriptions": subscriptions
    }


@router.post("/me/subscriptions", response_model=Subscription)
def create_user_subscription(
    *,
    db: Session = Depends(get_db),
    subscription_in: SubscriptionCreate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Create user subscription.
    """
    subscription = create_subscription(db, user_id=current_user.id, subscription=subscription_in)
    if not subscription:
        raise HTTPException(
            status_code=400,
            detail="Could not create subscription",
        )
    return subscription


@router.delete("/me/subscriptions/{subscription_id}", response_model=bool)
def delete_user_subscription(
    *,
    db: Session = Depends(get_db),
    subscription_id: int = Path(..., description="The ID of the subscription to delete"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Delete user subscription.
    """
    result = delete_subscription(db, user_id=current_user.id, subscription_id=subscription_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Subscription not found",
        )
    return result


@router.get("/me/favorites", response_model=List[NewsListItem])
def read_user_favorites(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user favorites.
    """
    favorites = get_favorites(db, user_id=current_user.id, skip=skip, limit=limit)
    
    # Convert to NewsListItem format
    result = []
    for news in favorites:
        item = {
            "id": news.id,
            "title": news.title,
            "url": news.url,
            "source_id": news.source_id,
            "source_name": news.source.name if news.source else "",
            "published_at": news.published_at,
            "image_url": news.image_url,
            "summary": news.summary,
            "category_id": news.category_id,
            "category_name": news.category.name if news.category else None,
            "is_top": news.is_top,
            "view_count": news.view_count,
            "sentiment_score": news.sentiment_score,
            "extra": news.extra,
            "created_at": news.created_at
        }
        result.append(item)
    
    return result


@router.post("/me/favorites/{news_id}", response_model=bool)
def add_user_favorite(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news to favorite"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Add news to favorites.
    """
    result = add_favorite(db, user_id=current_user.id, news_id=news_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="News not found",
        )
    return result


@router.delete("/me/favorites/{news_id}", response_model=bool)
def remove_user_favorite(
    *,
    db: Session = Depends(get_db),
    news_id: int = Path(..., description="The ID of the news to remove from favorites"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Remove news from favorites.
    """
    result = remove_favorite(db, user_id=current_user.id, news_id=news_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="News not found in favorites",
        )
    return result


@router.get("/me/history", response_model=List[NewsListItem])
def read_user_history(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get current user read history.
    """
    history = get_read_history(db, user_id=current_user.id, skip=skip, limit=limit)
    
    # Convert to NewsListItem format
    result = []
    for news in history:
        item = {
            "id": news.id,
            "title": news.title,
            "url": news.url,
            "source_id": news.source_id,
            "source_name": news.source.name if news.source else "",
            "published_at": news.published_at,
            "image_url": news.image_url,
            "summary": news.summary,
            "category_id": news.category_id,
            "category_name": news.category.name if news.category else None,
            "is_top": news.is_top,
            "view_count": news.view_count,
            "sentiment_score": news.sentiment_score,
            "extra": news.extra,
            "created_at": news.created_at
        }
        result.append(item)
    
    return result


@router.get("/{user_id}", response_model=UserSchema)
def read_user(
    *,
    db: Session = Depends(get_db),
    user_id: int = Path(..., description="The ID of the user to get"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Get user by ID.
    """
    user = get_user(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    return user


@router.put("/{user_id}", response_model=UserSchema)
def update_user_api(
    *,
    db: Session = Depends(get_db),
    user_id: int = Path(..., description="The ID of the user to update"),
    user_in: UserUpdate,
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Update a user.
    """
    user = get_user(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    
    if user_in.password:
        hashed_password = get_password_hash(user_in.password)
    else:
        hashed_password = None
    
    user = update_user(db, user_id=user_id, user=user_in, hashed_password=hashed_password)
    return user


@router.delete("/{user_id}", response_model=bool)
def delete_user_api(
    *,
    db: Session = Depends(get_db),
    user_id: int = Path(..., description="The ID of the user to delete"),
    _: Any = Depends(get_current_superuser),
) -> Any:
    """
    Delete a user.
    """
    user = get_user(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    
    result = delete_user(db, user_id=user_id)
    return result 