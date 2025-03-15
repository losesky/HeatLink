from celery.schedules import crontab

from worker.celery_app import celery_app

# 先导入 celery_app，然后再导入 tasks
# 这样可以避免循环导入问题
from worker.tasks import news


# Import all tasks
__all__ = ["news"]


# Define periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """
    Set up periodic tasks
    """
    # Fetch news from all sources every hour
    sender.add_periodic_task(
        crontab(minute=0, hour="*/1"),
        news.fetch_all_news.s(),
        name="fetch_all_news_hourly"
    )
    
    # Clean up old news every day at midnight
    sender.add_periodic_task(
        crontab(minute=0, hour=0),
        news.cleanup_old_news.s(days=30),
        name="cleanup_old_news_daily"
    ) 