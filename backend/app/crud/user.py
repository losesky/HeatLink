from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload

from app.models.user import User, Subscription
from app.models.news import News
from app.schemas.user import UserCreate, UserUpdate, SubscriptionCreate


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_users(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True
) -> List[User]:
    query = db.query(User)
    
    if active_only:
        query = query.filter(User.is_active == True)
    
    return query.offset(skip).limit(limit).all()


def create_user(db: Session, user: UserCreate, hashed_password: str) -> User:
    db_user = User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        is_active=user.is_active,
        is_superuser=user.is_superuser
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: int, user: UserUpdate, hashed_password: Optional[str] = None) -> Optional[User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    update_data = user.model_dump(exclude_unset=True)
    
    if hashed_password:
        update_data["hashed_password"] = hashed_password
    elif "password" in update_data:
        del update_data["password"]
    
    for key, value in update_data.items():
        setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    db_user = get_user(db, user_id)
    if not db_user:
        return False
    
    db.delete(db_user)
    db.commit()
    return True


def get_user_with_subscriptions(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    user = db.query(User).options(
        joinedload(User.subscriptions)
    ).filter(User.id == user_id).first()
    
    if not user:
        return None
    
    return {
        "user": user,
        "subscriptions": user.subscriptions
    }


def add_favorite(db: Session, user_id: int, news_id: int) -> bool:
    db_user = get_user(db, user_id)
    db_news = db.query(News).filter(News.id == news_id).first()
    
    if not db_user or not db_news:
        return False
    
    if db_news not in db_user.favorites:
        db_user.favorites.append(db_news)
        db.commit()
    
    return True


def remove_favorite(db: Session, user_id: int, news_id: int) -> bool:
    db_user = get_user(db, user_id)
    db_news = db.query(News).filter(News.id == news_id).first()
    
    if not db_user or not db_news:
        return False
    
    if db_news in db_user.favorites:
        db_user.favorites.remove(db_news)
        db.commit()
    
    return True


def get_favorites(db: Session, user_id: int, skip: int = 0, limit: int = 20) -> List[News]:
    db_user = get_user(db, user_id)
    if not db_user:
        return []
    
    return db_user.favorites[skip:skip + limit]


def add_read_history(db: Session, user_id: int, news_id: int) -> bool:
    db_user = get_user(db, user_id)
    db_news = db.query(News).filter(News.id == news_id).first()
    
    if not db_user or not db_news:
        return False
    
    if db_news not in db_user.read_history:
        db_user.read_history.append(db_news)
        db.commit()
    
    return True


def get_read_history(db: Session, user_id: int, skip: int = 0, limit: int = 20) -> List[News]:
    db_user = get_user(db, user_id)
    if not db_user:
        return []
    
    return db_user.read_history[skip:skip + limit]


def create_subscription(db: Session, user_id: int, subscription: SubscriptionCreate) -> Optional[Subscription]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    # Check if subscription already exists
    existing = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.type == subscription.type,
        Subscription.target_id == subscription.target_id
    ).first()
    
    if existing:
        return existing
    
    db_subscription = Subscription(
        user_id=user_id,
        type=subscription.type,
        target_id=subscription.target_id
    )
    
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription


def delete_subscription(db: Session, user_id: int, subscription_id: int) -> bool:
    db_subscription = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.user_id == user_id
    ).first()
    
    if not db_subscription:
        return False
    
    db.delete(db_subscription)
    db.commit()
    return True


def get_subscriptions(db: Session, user_id: int) -> List[Subscription]:
    return db.query(Subscription).filter(Subscription.user_id == user_id).all() 