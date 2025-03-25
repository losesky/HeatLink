from app.models.source import Source, SourceAlias, SourceType
from app.models.news import News, news_tag
from app.models.category import Category
from app.models.tag import Tag
from app.models.user import User, Subscription, user_favorite, user_read_history
from app.models.source_stats import SourceStats, ApiCallType
from app.models.proxy import ProxyConfig, ProxyProtocol, ProxyStatus

# For Alembic to detect all models
__all__ = [
    "Source", "SourceAlias", "SourceType",
    "News", "news_tag",
    "Category",
    "Tag",
    "User", "Subscription", "user_favorite", "user_read_history",
    "SourceStats", "ApiCallType",
    "ProxyConfig", "ProxyProtocol", "ProxyStatus"
] 