import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Table, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.session import Base


# Association table for User and News (favorites)
user_favorite = Table(
    "user_favorite",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("news_id", Integer, ForeignKey("news.id"), primary_key=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow)
)


# Association table for User and News (read history)
user_read_history = Table(
    "user_read_history",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("news_id", Integer, ForeignKey("news.id"), primary_key=True),
    Column("created_at", DateTime, default=datetime.datetime.utcnow)
)


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)  # 用户是否激活，与源表中的active字段无关
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    favorites = relationship("News", secondary=user_favorite)
    read_history = relationship("News", secondary=user_read_history)
    subscriptions = relationship("Subscription", back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)  # "source", "category", "tag"
    target_id = Column(String(50), nullable=False)  # ID of the source, category, or tag
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")
    
    __table_args__ = (
        # A user cannot subscribe to the same target multiple times
        UniqueConstraint('user_id', 'type', 'target_id', name='uix_user_subscription'),
    ) 