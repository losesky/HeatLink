from app.crud.source import (
    get_source, get_source_by_alias, get_sources, get_active_sources,
    create_source, update_source, delete_source,
    update_source_last_updated, increment_source_error_count,
    get_source_with_stats, create_source_alias, delete_source_alias
)
from app.crud.news import (
    get_news_by_id, get_news_by_original_id, get_news, get_news_with_relations,
    get_news_list_items, create_news, update_news, delete_news,
    increment_view_count, get_trending_news,
    add_tag_to_news, remove_tag_from_news,
    update_news_cluster, get_news_by_cluster
)
from app.crud.category import (
    get_category, get_category_by_slug, get_categories, get_root_categories,
    create_category, update_category, delete_category, get_category_tree
)
from app.crud.tag import (
    get_tag, get_tag_by_slug, get_tag_by_name, get_tags,
    create_tag, update_tag, delete_tag, get_or_create_tag
)
from app.crud.user import (
    get_user, get_user_by_email, get_user_by_username, get_users,
    create_user, update_user, delete_user, get_user_with_subscriptions,
    add_favorite, remove_favorite, get_favorites,
    add_read_history, get_read_history,
    create_subscription, delete_subscription, get_subscriptions
) 