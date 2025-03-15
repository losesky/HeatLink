import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, JSON, Table, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.session import Base


# Association table for News and Tag
news_tag = Table(
    "news_tag",
    Base.metadata,
    Column("news_id", Integer, ForeignKey("news.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True)
)


class News(Base):
    __tablename__ = "news"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    url = Column(String(512), nullable=False)
    mobile_url = Column(String(512), nullable=True)
    original_id = Column(String(255), nullable=False)  # Source site ID
    source_id = Column(String(50), ForeignKey("sources.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    is_top = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)
    sentiment_score = Column(Float, nullable=True)
    cluster_id = Column(String(50), nullable=True)  # Cluster ID
    extra = Column(JSON, nullable=True)  # Extra information, such as icons, heat, etc.
    
    # Relationships
    source = relationship("Source", back_populates="news")
    category = relationship("Category", back_populates="news")
    tags = relationship("Tag", secondary=news_tag, back_populates="news_items")
    
    __table_args__ = (
        # Only one record with the same original ID from the same source
        UniqueConstraint('source_id', 'original_id', name='uix_source_original'),
    ) 