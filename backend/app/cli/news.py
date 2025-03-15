import asyncio
import click
import json
import logging
from typing import List, Optional

from app.db.session import SessionLocal
from app.models.source import Source
from worker.sources.manager import source_manager
from worker.tasks.news import (
    fetch_high_frequency_sources,
    fetch_medium_frequency_sources,
    fetch_low_frequency_sources,
    fetch_source_news,
    fetch_all_news,
    cleanup_old_news,
    analyze_news_trends
)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@click.group()
def news():
    """新闻管理命令"""
    pass


@news.command("list-sources")
@click.option("--category", help="按分类筛选")
@click.option("--country", help="按国家筛选")
@click.option("--language", help="按语言筛选")
def list_sources(category: Optional[str], country: Optional[str], language: Optional[str]):
    """列出所有新闻源"""
    # 初始化新闻源
    from worker.tasks.news import init_sources
    init_sources()
    
    # 获取所有新闻源
    sources = source_manager.get_all_sources()
    
    # 应用筛选
    if category:
        sources = [s for s in sources if s.category == category]
    if country:
        sources = [s for s in sources if s.country == country]
    if language:
        sources = [s for s in sources if s.language == language]
    
    # 打印结果
    click.echo(f"找到 {len(sources)} 个新闻源:")
    for source in sources:
        click.echo(f"ID: {source.source_id}")
        click.echo(f"名称: {source.name}")
        click.echo(f"分类: {source.category}")
        click.echo(f"国家: {source.country}")
        click.echo(f"语言: {source.language}")
        click.echo(f"更新间隔: {source.update_interval}秒")
        click.echo("---")


@news.command("fetch")
@click.option("--source-id", help="指定新闻源ID")
@click.option("--frequency", type=click.Choice(["high", "medium", "low", "all"]), default="all", help="指定频率")
@click.option("--async", "is_async", is_flag=True, help="异步执行")
def fetch_news(source_id: Optional[str], frequency: str, is_async: bool):
    """抓取新闻"""
    if source_id:
        click.echo(f"抓取新闻源 {source_id} 的新闻...")
        if is_async:
            task = fetch_source_news.delay(source_id)
            click.echo(f"任务已提交，任务ID: {task.id}")
        else:
            result = fetch_source_news(source_id)
            click.echo(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if frequency == "high":
            click.echo("抓取高频新闻源的新闻...")
            if is_async:
                task = fetch_high_frequency_sources.delay()
                click.echo(f"任务已提交，任务ID: {task.id}")
            else:
                result = fetch_high_frequency_sources()
                click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        elif frequency == "medium":
            click.echo("抓取中频新闻源的新闻...")
            if is_async:
                task = fetch_medium_frequency_sources.delay()
                click.echo(f"任务已提交，任务ID: {task.id}")
            else:
                result = fetch_medium_frequency_sources()
                click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        elif frequency == "low":
            click.echo("抓取低频新闻源的新闻...")
            if is_async:
                task = fetch_low_frequency_sources.delay()
                click.echo(f"任务已提交，任务ID: {task.id}")
            else:
                result = fetch_low_frequency_sources()
                click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            click.echo("抓取所有新闻源的新闻...")
            if is_async:
                task = fetch_all_news.delay()
                click.echo(f"任务已提交，任务ID: {task.id}")
            else:
                result = fetch_all_news()
                click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@news.command("cleanup")
@click.option("--days", type=int, default=30, help="清理多少天前的新闻")
@click.option("--async", "is_async", is_flag=True, help="异步执行")
def cleanup(days: int, is_async: bool):
    """清理旧新闻"""
    click.echo(f"清理 {days} 天前的新闻...")
    if is_async:
        task = cleanup_old_news.delay(days)
        click.echo(f"任务已提交，任务ID: {task.id}")
    else:
        result = cleanup_old_news(days)
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@news.command("analyze")
@click.option("--days", type=int, default=7, help="分析最近多少天的新闻")
@click.option("--async", "is_async", is_flag=True, help="异步执行")
def analyze(days: int, is_async: bool):
    """分析新闻趋势"""
    click.echo(f"分析最近 {days} 天的新闻趋势...")
    if is_async:
        task = analyze_news_trends.delay(days)
        click.echo(f"任务已提交，任务ID: {task.id}")
    else:
        result = analyze_news_trends(days)
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@news.command("add-source")
@click.option("--id", "source_id", required=True, help="新闻源ID")
@click.option("--name", required=True, help="新闻源名称")
@click.option("--type", "source_type", required=True, type=click.Choice(["rss"]), help="新闻源类型")
@click.option("--url", required=True, help="新闻源URL")
@click.option("--category", help="分类")
@click.option("--country", help="国家")
@click.option("--language", help="语言")
@click.option("--update-interval", type=int, default=1800, help="更新间隔（秒）")
@click.option("--fetch-content", is_flag=True, help="是否获取完整内容")
@click.option("--content-selector", help="内容选择器")
def add_source(
    source_id: str,
    name: str,
    source_type: str,
    url: str,
    category: Optional[str],
    country: Optional[str],
    language: Optional[str],
    update_interval: int,
    fetch_content: bool,
    content_selector: Optional[str]
):
    """添加新闻源"""
    db = SessionLocal()
    try:
        # 检查是否已存在
        existing = db.query(Source).filter(Source.id == source_id).first()
        if existing:
            click.echo(f"新闻源 {source_id} 已存在，将更新")
            source = existing
        else:
            click.echo(f"创建新闻源 {source_id}")
            source = Source(id=source_id)
        
        # 更新属性
        source.name = name
        source.type = source_type
        source.url = url
        source.category = category
        source.country = country
        source.language = language
        source.update_interval = update_interval
        source.is_active = True
        
        # 配置
        config = {
            "fetch_content": fetch_content
        }
        if content_selector:
            config["content_selector"] = content_selector
        
        source.config = config
        
        # 保存到数据库
        db.add(source)
        db.commit()
        
        click.echo(f"新闻源 {source_id} 已保存")
    except Exception as e:
        db.rollback()
        click.echo(f"错误: {str(e)}")
    finally:
        db.close()


@news.command("test-source")
@click.option("--id", "source_id", required=True, help="新闻源ID")
@click.option("--type", "source_type", required=True, type=click.Choice(["rss"]), help="新闻源类型")
@click.option("--url", required=True, help="新闻源URL")
@click.option("--fetch-content", is_flag=True, help="是否获取完整内容")
@click.option("--content-selector", help="内容选择器")
def test_source(
    source_id: str,
    source_type: str,
    url: str,
    fetch_content: bool,
    content_selector: Optional[str]
):
    """测试新闻源"""
    click.echo(f"测试新闻源 {source_id}...")
    
    # 初始化新闻源
    from worker.sources.rss import RSSNewsSource
    
    config = {
        "fetch_content": fetch_content
    }
    if content_selector:
        config["content_selector"] = content_selector
    
    if source_type == "rss":
        source = RSSNewsSource(
            source_id=source_id,
            name=source_id,
            feed_url=url,
            config=config
        )
    else:
        click.echo(f"不支持的新闻源类型: {source_type}")
        return
    
    # 抓取新闻
    try:
        news_items = asyncio.run(source.process())
        click.echo(f"成功获取 {len(news_items)} 条新闻")
        
        # 打印第一条新闻
        if news_items:
            click.echo("第一条新闻:")
            item = news_items[0]
            click.echo(f"标题: {item.title}")
            click.echo(f"URL: {item.url}")
            click.echo(f"发布时间: {item.published_at}")
            if item.summary:
                click.echo(f"摘要: {item.summary[:100]}...")
            if item.image_url:
                click.echo(f"图片: {item.image_url}")
    except Exception as e:
        click.echo(f"错误: {str(e)}")


if __name__ == "__main__":
    news() 