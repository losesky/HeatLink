import logging
from typing import Dict, Any, Optional, List, Type

from worker.sources.base import NewsSource
from worker.sources.rss import RSSNewsSource, RSSSourceFactory
from worker.sources.sites import (
    ZhihuHotNewsSource,
    WeiboHotNewsSource,
    BaiduHotNewsSource,
    HackerNewsSource,
    BilibiliHotNewsSource,
    DouyinHotNewsSource,
    ToutiaoHotNewsSource,
    ITHomeNewsSource,
    GitHubTrendingSource,
    V2EXSeleniumSource,
    XueqiuHotStockSource,
    TiebaHotTopicSource,
    KuaishouHotSearchSource,
    Jin10NewsSource,
    CanKaoXiaoXiNewsSource,
    SolidotNewsSource,
    ZaoBaoNewsSource,
    SputnikNewsCNSource,
    ProductHuntNewsSource,
    LinuxDoNewsSource,
    LinuxDoLatestNewsSource,
    LinuxDoHotNewsSource,
    KaoPuNewsSource,
    GeLongHuiNewsSource,
    FastBullExpressNewsSource,
    FastBullGeneralNewsSource,
    WallStreetCNLiveNewsSource,
    WallStreetCNNewsSource,
    WallStreetCNHotNewsSource,
    Kr36NewsSource,
    CoolApkNewsSource,
    CoolApkFeedNewsSource,
    CoolApkAppNewsSource,
    CLSNewsSource,
    BBCWorldNewsSource,
    ThePaperSeleniumSource,
    ZhihuDailyNewsSource,
    BloombergNewsSource,
    BloombergMarketsNewsSource,
    BloombergTechnologyNewsSource,
    YiCaiBriefSource,
    YiCaiNewsSource,
    IfengStudioSource,
    IfengTechSource
)

logger = logging.getLogger(__name__)


class NewsSourceFactory:
    """
    新闻源工厂类
    用于创建各种新闻源适配器
    """
    
    @staticmethod
    def create_source(source_type: str, **kwargs) -> Optional[NewsSource]:
        """
        Create a news source based on type
        
        Args:
            source_type: Source type (e.g., "zhihu", "weibo", "hackernews")
            **kwargs: Additional arguments to pass to the source constructor
            
        Returns:
            NewsSource: News source instance
        """
        if source_type == "zhihu":
            return ZhihuHotNewsSource(**kwargs)
        elif source_type == "weibo":
            return WeiboHotNewsSource(**kwargs)
        elif source_type == "baidu":
            return BaiduHotNewsSource(**kwargs)
        elif source_type == "hackernews":
            return HackerNewsSource(**kwargs)
        elif source_type == "bilibili":
            return BilibiliHotNewsSource(**kwargs)
        elif source_type == "douyin":
            return DouyinHotNewsSource(**kwargs)
        elif source_type == "toutiao":
            return ToutiaoHotNewsSource(**kwargs)
        elif source_type == "thepaper":
            return ThePaperSeleniumSource(**kwargs)
        elif source_type == "ithome":
            return ITHomeNewsSource(**kwargs)
        elif source_type == "github":
            return GitHubTrendingSource(**kwargs)
        elif source_type == "v2ex":
            return V2EXSeleniumSource(**kwargs)
        elif source_type == "xueqiu":
            return XueqiuHotStockSource(**kwargs)
        elif source_type == "tieba":
            return TiebaHotTopicSource(**kwargs)
        elif source_type == "kuaishou":
            return KuaishouHotSearchSource(**kwargs)
        elif source_type == "jin10":
            return Jin10NewsSource(**kwargs)
        elif source_type == "cankaoxiaoxi":
            return CanKaoXiaoXiNewsSource(**kwargs)
        elif source_type == "solidot":
            return SolidotNewsSource(**kwargs)
        elif source_type == "zaobao":
            return ZaoBaoNewsSource(**kwargs)
        elif source_type == "sputniknewscn":
            return SputnikNewsCNSource(**kwargs)
        elif source_type == "producthunt":
            return ProductHuntNewsSource(**kwargs)
        elif source_type == "linuxdo":
            return LinuxDoNewsSource(**kwargs)
        elif source_type == "linuxdo-latest":
            return LinuxDoLatestNewsSource(**kwargs)
        elif source_type == "linuxdo-hot":
            return LinuxDoHotNewsSource(**kwargs)
        elif source_type == "kaopu":
            return KaoPuNewsSource(**kwargs)
        elif source_type == "gelonghui":
            return GeLongHuiNewsSource(**kwargs)
        elif source_type == "fastbull":
            return FastBullExpressNewsSource(**kwargs)
        elif source_type == "fastbull-express":
            return FastBullExpressNewsSource(**kwargs)
        elif source_type == "fastbull-news":
            return FastBullGeneralNewsSource(**kwargs)
        elif source_type == "wallstreetcn":
            return WallStreetCNLiveNewsSource(**kwargs)
        elif source_type == "wallstreetcn-news":
            return WallStreetCNNewsSource(**kwargs)
        elif source_type == "wallstreetcn-hot":
            return WallStreetCNHotNewsSource(**kwargs)
        elif source_type == "36kr":
            return Kr36NewsSource(**kwargs)
        elif source_type == "coolapk":
            return CoolApkNewsSource(**kwargs)
        elif source_type == "coolapk-feed":
            return CoolApkFeedNewsSource(**kwargs)
        elif source_type == "coolapk-app":
            return CoolApkAppNewsSource(**kwargs)
        elif source_type == "cls":
            return CLSNewsSource(**kwargs)
        elif source_type == "cls-article":  # 处理被合并的源的兼容性
            logger.info("cls-article已被合并到cls中，使用cls源替代")
            return CLSNewsSource(source_id="cls", **kwargs)
        elif source_type == "bbc_world":
            return BBCWorldNewsSource(**kwargs)
        elif source_type == "bloomberg":
            return BloombergNewsSource(**kwargs)
        elif source_type == "bloomberg-markets":
            return BloombergMarketsNewsSource(**kwargs)
        elif source_type == "bloomberg-tech":
            return BloombergTechnologyNewsSource(**kwargs)
        elif source_type == "bloomberg-china":  # 处理被合并的源的兼容性
            logger.info("bloomberg-china已被合并到bloomberg中，使用bloomberg源替代")
            return BloombergNewsSource(source_id="bloomberg", country="CN", **kwargs)
        elif source_type == "yicai-brief":
            return YiCaiBriefSource(**kwargs)
        elif source_type == "yicai-news":
            return YiCaiNewsSource(**kwargs)
        elif source_type == "ifeng-studio":
            return IfengStudioSource(**kwargs)
        elif source_type == "ifeng-tech":
            return IfengTechSource(**kwargs)
        elif source_type == "ifanr":
            return RSSNewsSource(
                source_id="ifanr",
                name="爱范儿",
                feed_url="https://www.ifanr.com/feed",
                category="technology",
                country="CN",
                language="zh-CN",
                update_interval=1800,  # 30分钟更新一次
                config={
                    "fetch_content": True,
                    "content_selector": ".article-content"
                },
                **kwargs
            )
        elif source_type == "techcrunch":
            return RSSNewsSource(
                source_id="techcrunch",
                name="TechCrunch",
                feed_url="https://techcrunch.com/feed/",
                category="technology",
                country="US",
                language="en",
                update_interval=1800,  # 30分钟更新一次
                config={
                    "fetch_content": True,
                    "content_selector": ".article-content"
                },
                **kwargs
            )
        elif source_type == "the_verge":
            return RSSNewsSource(
                source_id="the_verge",
                name="The Verge",
                feed_url="https://www.theverge.com/rss/index.xml",
                category="technology",
                country="US",
                language="en",
                update_interval=1800,  # 30分钟更新一次
                config={
                    "fetch_content": True,
                    "content_selector": ".c-entry-content"
                },
                **kwargs
            )
        elif source_type == "zhihu_daily":
            return ZhihuDailyNewsSource(**kwargs)
        else:
            logger.error(f"Unknown source type: {source_type}")
            return None
    
    @staticmethod
    def create_default_sources() -> List[NewsSource]:
        """
        创建默认的新闻源适配器
        """
        # 获取所有可用的源类型
        source_types = NewsSourceFactory.get_available_sources()
        
        # 创建所有源的实例
        sources = []
        for source_type in source_types:
            try:
                source = NewsSourceFactory.create_source(source_type)
                if source:
                    sources.append(source)
            except Exception as e:
                logger.error(f"创建源 {source_type} 时出错: {str(e)}")
        
        logger.info(f"成功创建了 {len(sources)} 个新闻源适配器")
        return sources
    
    @staticmethod
    def get_available_sources() -> List[str]:
        """
        获取所有可用的新闻源类型
        """
        try:
            # 首先尝试从数据库中获取所有源类型
            # 需要导入这些模块以便访问数据库
            import os
            import sys
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            sys.path.insert(0, base_dir)
            
            from app.db.session import SessionLocal
            from sqlalchemy import text
            
            # 创建数据库会话
            db = SessionLocal()
            try:
                # 查询数据库中的所有源类型，不再限制状态为ACTIVE
                                # 查询数据库中的所有源类型
                result = db.execute(text("SELECT id FROM sources WHERE status = 'ACTIVE'"))
                db_sources = [row[0] for row in result]
                
                # 排除通用的"rss"类型，因为它需要额外的参数
                if "rss" in db_sources:
                    db_sources.remove("rss")
                
                if db_sources:
                    logger.info(f"从数据库获取了 {len(db_sources)} 个新闻源类型")
                    return db_sources
                else:
                    logger.warning("数据库中没有找到新闻源，将使用硬编码列表")
            except Exception as e:
                logger.error(f"从数据库获取新闻源类型失败: {str(e)}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"初始化数据库连接失败: {str(e)}")
        
        # 如果从数据库获取失败或没有找到数据，使用硬编码列表作为备用
        # 手动定义所有支持的新闻源类型
        sources = [
            "zhihu", "weibo", "baidu", "hackernews", "bilibili", "douyin",
            "toutiao", "ithome", "github", "v2ex", "xueqiu",
            "tieba", "kuaishou", "jin10", "cankaoxiaoxi", "solidot", "zaobao",
            "sputniknewscn", "producthunt", "linuxdo", "linuxdo-latest", "linuxdo-hot",
            "kaopu", "gelonghui", "fastbull", "fastbull-express", "fastbull-news", "wallstreetcn",
            "wallstreetcn-news", "wallstreetcn-hot", "36kr", "coolapk", "coolapk-feed",
            "coolapk-app", "cls", "bbc_world", "thepaper",
            "zhihu_daily", "bloomberg", "bloomberg-markets", "bloomberg-tech", "yicai-brief", "yicai-news", "ifeng-studio", "ifeng-tech", "ifanr", "techcrunch", "the_verge"
        ]
        # 排除通用的"rss"类型，因为它需要额外的参数
        if "rss" in sources:
            sources.remove("rss")
            
        logger.info(f"使用硬编码列表提供 {len(sources)} 个新闻源类型")
        return sources 