from app.models.source import Source, SourceAlias, SourceType
from app.models.news import News, news_tag
from app.models.category import Category
from app.models.tag import Tag
from app.models.user import User, Subscription, user_favorite, user_read_history

# For Alembic to detect all models
__all__ = [
    "Source", "SourceAlias", "SourceType",
    "News", "news_tag",
    "Category",
    "Tag",
    "User", "Subscription", "user_favorite", "user_read_history"
] 