import logging
from typing import Dict, Any, Optional, List, Type

from worker.sources.base import NewsSource
from worker.sources.rss import RSSNewsSource, RSSSourceFactory
from worker.sources.sites import (
    ZhihuHotNewsSource,
    WeiboHotNewsSource,
    BaiduHotNewsSource,
    ThePaperHotNewsSource,
    HackerNewsSource,
    BilibiliHotNewsSource,
    DouyinHotNewsSource,
    ToutiaoHotNewsSource,
    ITHomeNewsSource,
    GitHubTrendingSource,
    V2EXHotTopicsSource,
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
    CLSArticleNewsSource
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
        创建新闻源适配器
        """
        if source_type == "rss":
            return RSSSourceFactory.create_source(**kwargs)
        elif source_type == "zhihu":
            return ZhihuHotNewsSource(**kwargs)
        elif source_type == "weibo":
            return WeiboHotNewsSource(**kwargs)
        elif source_type == "baidu":
            return BaiduHotNewsSource(**kwargs)
        elif source_type == "thepaper":
            return ThePaperHotNewsSource(**kwargs)
        elif source_type == "hackernews":
            return HackerNewsSource(**kwargs)
        elif source_type == "bilibili":
            return BilibiliHotNewsSource(**kwargs)
        elif source_type == "douyin":
            return DouyinHotNewsSource(**kwargs)
        elif source_type == "toutiao":
            return ToutiaoHotNewsSource(**kwargs)
        elif source_type == "ithome":
            return ITHomeNewsSource(**kwargs)
        elif source_type == "github":
            return GitHubTrendingSource(**kwargs)
        elif source_type == "v2ex":
            return V2EXHotTopicsSource(**kwargs)
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
        elif source_type == "cls-article":
            return CLSArticleNewsSource(**kwargs)
        else:
            logger.error(f"Unknown source type: {source_type}")
            return None
    
    @staticmethod
    def create_default_sources() -> List[NewsSource]:
        """
        创建默认的新闻源适配器
        """
        sources = []
        
        # 添加知乎热榜
        sources.append(ZhihuHotNewsSource())
        
        # 添加微博热搜
        sources.append(WeiboHotNewsSource())
        
        # 添加百度热搜
        sources.append(BaiduHotNewsSource())
        
        # 添加澎湃新闻热榜
        sources.append(ThePaperHotNewsSource())
        
        # 添加Hacker News
        sources.append(HackerNewsSource())
        
        # 添加B站热搜
        sources.append(BilibiliHotNewsSource())
        
        # 添加抖音热搜
        sources.append(DouyinHotNewsSource())
        
        # 添加今日头条热搜
        sources.append(ToutiaoHotNewsSource())
        
        # 添加IT之家
        sources.append(ITHomeNewsSource())
        
        # 添加GitHub Trending
        sources.append(GitHubTrendingSource())
        
        # 添加V2EX热门
        sources.append(V2EXHotTopicsSource())
        
        # 添加雪球热门股票
        sources.append(XueqiuHotStockSource())
        
        # 添加贴吧热门话题
        sources.append(TiebaHotTopicSource())
        
        # 添加快手热搜
        sources.append(KuaishouHotSearchSource())
        
        # 添加金十数据快讯
        sources.append(Jin10NewsSource())
        
        # 添加参考消息
        sources.append(CanKaoXiaoXiNewsSource())
        
        # 添加奇客
        sources.append(SolidotNewsSource())
        
        # 添加早报
        sources.append(ZaoBaoNewsSource())
        
        # 添加卫星通讯社
        sources.append(SputnikNewsCNSource())
        
        # 添加Product Hunt
        sources.append(ProductHuntNewsSource())
        
        # 添加Linux中国
        sources.append(LinuxDoNewsSource())
        
        # 添加靠谱新闻
        sources.append(KaoPuNewsSource())
        
        # 添加格隆汇
        sources.append(GeLongHuiNewsSource())
        
        # 添加快牛快讯
        sources.append(FastBullExpressNewsSource())
        
        # 添加快牛新闻
        sources.append(FastBullGeneralNewsSource())
        
        # 添加华尔街见闻快讯
        sources.append(WallStreetCNLiveNewsSource())
        
        # 添加华尔街见闻文章
        sources.append(WallStreetCNNewsSource())
        
        # 添加华尔街见闻热门
        sources.append(WallStreetCNHotNewsSource())
        
        # 添加36氪快讯
        sources.append(Kr36NewsSource())
        
        # 添加酷安头条
        sources.append(CoolApkNewsSource())
        
        # 添加财联社快讯
        sources.append(CLSNewsSource())
        
        # 添加RSS新闻源
        sources.append(RSSSourceFactory.create_zhihu_daily())
        sources.append(RSSSourceFactory.create_hacker_news())
        sources.append(RSSSourceFactory.create_bbc_news())
        
        # 添加一些中文科技新闻源
        sources.append(RSSNewsSource(
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
            }
        ))
        
        # 添加一些英文科技新闻源
        sources.append(RSSNewsSource(
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
            }
        ))
        
        sources.append(RSSNewsSource(
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
            }
        ))
        
        return sources 