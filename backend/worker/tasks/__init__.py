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
    # 新增：单源调度任务 - 每5分钟检查一次需要更新的源
    sender.add_periodic_task(
        300.0,  # 5分钟
        news.schedule_source_updates.s(),
        name="schedule_source_updates",
        queue="news-queue"
    )
    
    # 高频更新源（每10分钟更新一次）- 社交媒体热搜类
    sender.add_periodic_task(
        600.0,  # 10分钟
        news.fetch_high_frequency_sources.s(),
        name="fetch_high_frequency_sources",
        queue="news-queue"
    )
    
    # 中频更新源（每30分钟更新一次）- 新闻网站
    sender.add_periodic_task(
        1800.0,  # 30分钟
        news.fetch_medium_frequency_sources.s(),
        name="fetch_medium_frequency_sources",
        queue="news-queue"
    )
    
    # 低频更新源（每小时更新一次）- 其他资讯
    sender.add_periodic_task(
        3600.0,  # 60分钟
        news.fetch_low_frequency_sources.s(),
        name="fetch_low_frequency_sources",
        queue="news-queue"
    )
    
    # 每天凌晨3点清理过期新闻（30天前的新闻）
    sender.add_periodic_task(
        crontab(minute=0, hour=3),
        news.cleanup_old_news.s(days=30),
        name="cleanup_old_news_daily",
        queue="news-queue"
    )
    
    # 每周日凌晨4点进行数据分析和聚合
    sender.add_periodic_task(
        crontab(minute=0, hour=4, day_of_week=0),
        news.analyze_news_trends.s(days=7),
        name="analyze_news_trends_weekly",
        queue="news-queue"
    )

# 也可以使用 beat_schedule 配置
celery_app.conf.beat_schedule = {
    # 新增：单源调度任务（每5分钟）
    'schedule-source-updates': {
        'task': 'news.schedule_source_updates',
        'schedule': 300.0,  # 5分钟
        'options': {
            'queue': 'news-queue',
        }
    },
    
    # 高频新闻源抓取任务（每10分钟）
    'fetch-high-frequency-sources': {
        'task': 'news.fetch_high_frequency_sources',
        'schedule': 600.0,  # 10分钟
        'options': {
            'queue': 'news-queue',
        }
    },
    
    # 中频新闻源抓取任务（每30分钟）
    'fetch-medium-frequency-sources': {
        'task': 'news.fetch_medium_frequency_sources',
        'schedule': 1800.0,  # 30分钟
        'options': {
            'queue': 'news-queue',
        }
    },
    
    # 低频新闻源抓取任务（每小时）
    'fetch-low-frequency-sources': {
        'task': 'news.fetch_low_frequency_sources',
        'schedule': 3600.0,  # 1小时
        'options': {
            'queue': 'news-queue',
        }
    },
    
    # 清理旧新闻任务（每天凌晨3点）
    'cleanup-old-news': {
        'task': 'news.cleanup_old_news',
        'schedule': crontab(hour=3, minute=0),
        'args': (30,),  # 清理30天前的新闻
        'options': {
            'queue': 'news-queue',
        }
    },
    
    # 新闻趋势分析任务（每周日凌晨4点）
    'analyze-news-trends': {
        'task': 'news.analyze_news_trends',
        'schedule': crontab(hour=4, minute=0, day_of_week=0),
        'args': (7,),  # 分析最近7天的新闻
        'options': {
            'queue': 'news-queue',
        }
    },
} 