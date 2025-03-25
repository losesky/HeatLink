# 导入所有新闻源适配器
from worker.sources.sites.zhihu import ZhihuHotNewsSource
from worker.sources.sites.weibo import WeiboHotNewsSource
from worker.sources.sites.baidu import BaiduHotNewsSource
from worker.sources.sites.hackernews import HackerNewsSource
from worker.sources.sites.bilibili import BilibiliHotNewsSource
from worker.sources.sites.douyin import DouyinHotNewsSource
from worker.sources.sites.toutiao import ToutiaoHotNewsSource
from worker.sources.sites.ithome import ITHomeNewsSource
from worker.sources.sites.github import GitHubTrendingSource
from worker.sources.sites.v2ex import V2EXSeleniumSource
from worker.sources.sites.xueqiu import XueqiuHotStockSource
from worker.sources.sites.tieba import TiebaHotTopicSource
from worker.sources.sites.kuaishou import KuaishouHotSearchSource
from worker.sources.sites.jin10 import Jin10NewsSource
from worker.sources.sites.cankaoxiaoxi import CanKaoXiaoXiNewsSource
from worker.sources.sites.solidot import SolidotNewsSource
from worker.sources.sites.zaobao import ZaoBaoNewsSource
from worker.sources.sites.sputniknewscn import SputnikNewsCNSource
from worker.sources.sites.producthunt import ProductHuntNewsSource
from worker.sources.sites.linuxdo import LinuxDoNewsSource, LinuxDoLatestNewsSource, LinuxDoHotNewsSource
from worker.sources.sites.kaopu import KaoPuNewsSource
from worker.sources.sites.gelonghui import GeLongHuiNewsSource
from worker.sources.sites.fastbull import FastBullExpressNewsSource, FastBullGeneralNewsSource
from worker.sources.sites.wallstreetcn import (
    WallStreetCNLiveNewsSource,
    WallStreetCNNewsSource,
    WallStreetCNHotNewsSource
)
# 36kr模块名称需要使用引号，因为Python不允许模块名以数字开头
from worker.sources.sites.kr36 import Kr36NewsSource
# 新增适配器
from worker.sources.sites.coolapk import CoolApkNewsSource, CoolApkFeedNewsSource, CoolApkAppNewsSource
from worker.sources.sites.cls import CLSNewsSource, CLSArticleNewsSource
# 添加BBC世界新闻适配器
from worker.sources.sites.bbc import BBCWorldNewsSource
# 添加新创建的澎湃新闻Selenium适配器
from worker.sources.sites.thepaper_selenium import ThePaperSeleniumSource
# 添加知乎日报适配器
from worker.sources.sites.zhihu_daily import ZhihuDailyNewsSource
# 添加彭博社新闻适配器
from worker.sources.sites.bloomberg import (
    BloombergNewsSource,
    BloombergMarketsNewsSource,
    BloombergTechnologyNewsSource, 
    BloombergChinaNewsSource
)

# 导出所有新闻源适配器
__all__ = [
    "ZhihuHotNewsSource",
    "WeiboHotNewsSource",
    "BaiduHotNewsSource",
    "HackerNewsSource",
    "BilibiliHotNewsSource",
    "DouyinHotNewsSource",
    "ToutiaoHotNewsSource",
    "ITHomeNewsSource",
    "GitHubTrendingSource",
    "V2EXSeleniumSource",
    "XueqiuHotStockSource",
    "TiebaHotTopicSource",
    "KuaishouHotSearchSource",
    "Jin10NewsSource",
    "CanKaoXiaoXiNewsSource",
    "SolidotNewsSource",
    "ZaoBaoNewsSource",
    "SputnikNewsCNSource",
    "ProductHuntNewsSource",
    "LinuxDoNewsSource",
    "LinuxDoLatestNewsSource",
    "LinuxDoHotNewsSource",
    "KaoPuNewsSource",
    "GeLongHuiNewsSource",
    "FastBullExpressNewsSource",
    "FastBullGeneralNewsSource",
    "WallStreetCNLiveNewsSource",
    "WallStreetCNNewsSource",
    "WallStreetCNHotNewsSource",
    "Kr36NewsSource",
    "CoolApkNewsSource",
    "CoolApkFeedNewsSource",
    "CoolApkAppNewsSource",
    "CLSNewsSource",
    "CLSArticleNewsSource",
    "BBCWorldNewsSource",
    "ThePaperSeleniumSource",
    "ZhihuDailyNewsSource",
    "BloombergNewsSource",
    "BloombergMarketsNewsSource",
    "BloombergTechnologyNewsSource",
    "BloombergChinaNewsSource"
] 