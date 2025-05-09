#!/usr/bin/env python
"""
初始化脚本：将新闻源导入到数据库中
"""
import sys
import os
import datetime
import json
from pathlib import Path

from sqlalchemy import true

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 确保加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.source import Source, SourceType, SourceStatus
from app.models.category import Category

# 新闻源分类
CATEGORIES = {
    "news": "新闻资讯",
    "tech": "科技",
    "finance": "财经",
    "social": "社交媒体",
    "forum": "论坛社区",
    "dev": "开发者",
    "knowledge": "知识"
}

# 新闻源数据
SOURCES = [
    {
        "id": "36kr",
        "name": "36氪",
        "description": "36氪快讯，互联网创业资讯",
        "url": "https://www.36kr.com/newsflashes",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "selector": ".newsflash-item",
            "title_selector": "a.item-title",
            "date_selector": ".time",
            "date_format": "relative"
        }
    },
    {
        "id": "baidu",
        "name": "百度热搜",
        "description": "百度实时热搜榜单",
        "url": "https://top.baidu.com/board?tab=realtime",
        "type": SourceType.API,
        "category": "social",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://top.baidu.com/board?tab=realtime",
            "data_path": "data.cards[0].content"
        }
    },
    {
        "id": "bilibili",
        "name": "哔哩哔哩热搜",
        "description": "B站热搜榜单",
        "url": "https://www.bilibili.com/",
        "type": SourceType.API,
        "category": "social",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://s.search.bilibili.com/main/hotword?limit=30"
        }
    },
    {
        "id": "cankaoxiaoxi",
        "name": "参考消息",
        "description": "参考消息网站新闻",
        "url": "https://china.cankaoxiaoxi.com/",
        "type": SourceType.API,
        "category": "news",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_urls": [
                "https://china.cankaoxiaoxi.com/json/channel/zhongguo/list.json",
                "https://china.cankaoxiaoxi.com/json/channel/guandian/list.json",
                "https://china.cankaoxiaoxi.com/json/channel/gj/list.json"
            ]
        }
    },
    {
        "id": "douyin",
        "name": "抖音热搜",
        "description": "抖音热搜榜单",
        "url": "https://www.douyin.com/",
        "type": SourceType.API,
        "category": "social",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1"
        }
    },
    {
        "id": "fastbull-express",
        "name": "FastBull快讯",
        "description": "FastBull财经快讯",
        "url": "https://www.fastbull.com/cn/express-news",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "selector": ".news-list",
            "title_selector": ".title_name",
            "date_selector": "[data-date]"
        }
    },
    {
        "id": "fastbull-news",
        "name": "FastBull新闻",
        "description": "FastBull财经新闻",
        "url": "https://www.fastbull.com/cn/news",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "selector": ".trending_type",
            "title_selector": ".title",
            "date_selector": "[data-date]"
        }
    },
    {
        "id": "gelonghui",
        "name": "格隆汇",
        "description": "格隆汇财经资讯",
        "url": "https://www.gelonghui.com/news/",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "selector": ".article-content",
            "title_selector": ".detail-right>a h2",
            "date_selector": ".time > span:nth-child(3)"
        }
    },
    {
        "id": "github",
        "name": "GitHub Trending",
        "description": "GitHub 趋势项目",
        "url": "https://github.com/trending",
        "type": SourceType.WEB,
        "category": "dev",
        "country": "全球",
        "language": "en",
        "config": {
            "selector": "main .Box div[data-hpc] > article",
            "title_selector": ">h2 a",
            "info_selector": "[href$=stargazers]"
        }
    },
    {
        "id": "hackernews",
        "name": "Hacker News",
        "description": "Hacker News 科技新闻",
        "url": "https://news.ycombinator.com",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "美国",
        "language": "en",
        "config": {
            "selector": ".athing",
            "title_selector": ".titleline a",
            "score_selector": "#score_{id}"
        }
    },
    {
        "id": "ithome",
        "name": "IT之家",
        "description": "IT之家科技资讯",
        "url": "https://www.ithome.com/list/",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "selector": "#list > div.fl > ul > li",
            "title_selector": "a.t",
            "date_selector": "i"
        }
    },
    {
        "id": "jin10",
        "name": "金十数据",
        "description": "金十财经快讯",
        "url": "https://www.jin10.com/",
        "type": SourceType.API,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://www.jin10.com/flash_newest.js"
        }
    },
    {
        "id": "kaopu",
        "name": "靠谱新闻",
        "description": "靠谱新闻聚合",
        "url": "https://kaopucdn.azureedge.net/",
        "type": SourceType.API,
        "category": "news",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_urls": [
                "https://kaopucdn.azureedge.net/jsondata/news_list_beta_hans_0.json",
                "https://kaopucdn.azureedge.net/jsondata/news_list_beta_hans_1.json"
            ]
        }
    },
    {
        "id": "kuaishou",
        "name": "快手热搜",
        "description": "快手热搜榜单",
        "url": "https://www.kuaishou.com/",
        "type": SourceType.WEB,
        "category": "social",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "data_pattern": "window\\.__APOLLO_STATE__\\s*=\\s*(\\{.+?\\});"
        }
    },
    {
        "id": "linuxdo",
        "name": "Linux中国论坛",
        "description": "Linux中国社区最新帖子",
        "url": "https://linux.do/latest.json?order=created",
        "type": SourceType.API,
        "category": "dev",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://linux.do/latest.json?order=created",
            "data_path": "topic_list.topics"
        }
    },
    {
        "id": "linuxdo-hot",
        "name": "Linux中国热门",
        "description": "Linux中国社区热门帖子",
        "url": "https://linux.do/top/daily.json",
        "type": SourceType.API,
        "category": "dev",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://linux.do/top/daily.json",
            "data_path": "topic_list.topics"
        }
    },
    {
        "id": "producthunt",
        "name": "Product Hunt",
        "description": "Product Hunt 产品发现平台",
        "url": "https://www.producthunt.com/",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "美国",
        "language": "en",
        "config": {
            "selector": "[data-test=homepage-section-0] [data-test^=post-item]",
            "title_selector": "a[data-test^=post-name]",
            "vote_selector": "[data-test=vote-button]"
        }
    },
    {
        "id": "solidot",
        "name": "Solidot",
        "description": "Solidot奇客资讯",
        "url": "https://www.solidot.org",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "selector": ".block_m",
            "title_selector": ".bg_htit a",
            "date_selector": ".talk_time"
        }
    },
    {
        "id": "sputniknewscn",
        "name": "俄罗斯卫星通讯社",
        "description": "俄罗斯卫星通讯社中文网",
        "url": "https://sputniknews.cn/services/widget/lenta/",
        "type": SourceType.WEB,
        "category": "news",
        "country": "俄罗斯",
        "language": "zh-CN",
        "config": {
            "selector": ".lenta__item",
            "title_selector": ".lenta__item-text",
            "date_selector": ".lenta__item-date"
        }
    },
    {
        "id": "thepaper",
        "name": "澎湃新闻热榜",
        "description": "澎湃新闻热榜（使用Selenium自动获取）",
        "url": "https://www.thepaper.cn/",
        "type": SourceType.WEB,
        "category": "news",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "use_selenium": true,
            "headless": true
        }
    },
    {
        "id": "tieba",
        "name": "百度贴吧",
        "description": "百度贴吧热门话题",
        "url": "https://tieba.baidu.com/",
        "type": SourceType.API,
        "category": "social",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://tieba.baidu.com/hottopic/browse/topicList",
            "data_path": "data.bang_topic.topic_list"
        }
    },
    {
        "id": "toutiao",
        "name": "今日头条",
        "description": "今日头条热榜",
        "url": "https://www.toutiao.com/",
        "type": SourceType.API,
        "category": "news",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
            "data_path": "data"
        }
    },
    {
        "id": "v2ex",
        "name": "V2EX",
        "description": "V2EX创意工作者社区",
        "url": "https://www.v2ex.com/",
        "type": SourceType.API,
        "category": "dev",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_urls": [
                "https://www.v2ex.com/feed/create.json",
                "https://www.v2ex.com/feed/ideas.json",
                "https://www.v2ex.com/feed/programmer.json",
                "https://www.v2ex.com/feed/share.json"
            ]
        }
    },
    {
        "id": "wallstreetcn",
        "name": "华尔街见闻快讯",
        "description": "华尔街见闻实时快讯",
        "url": "https://wallstreetcn.com/live",
        "type": SourceType.API,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=30",
            "data_path": "data.items"
        }
    },
    {
        "id": "wallstreetcn-news",
        "name": "华尔街见闻资讯",
        "description": "华尔街见闻新闻资讯",
        "url": "https://wallstreetcn.com/news",
        "type": SourceType.API,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://api-one.wallstcn.com/apiv1/content/information-flow?channel=global-channel&accept=article&limit=30",
            "data_path": "data.items"
        }
    },
    {
        "id": "wallstreetcn-hot",
        "name": "华尔街见闻热门",
        "description": "华尔街见闻热门文章",
        "url": "https://wallstreetcn.com/",
        "type": SourceType.API,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://api-one.wallstcn.com/apiv1/content/articles/hot?period=all",
            "data_path": "data.day_items"
        }
    },
    {
        "id": "weibo",
        "name": "微博热搜",
        "description": "新浪微博热搜榜",
        "url": "https://weibo.com/",
        "type": SourceType.API,
        "category": "social",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://weibo.com/ajax/side/hotSearch",
            "data_path": "data.realtime"
        }
    },
    {
        "id": "xueqiu",
        "name": "雪球热股",
        "description": "雪球财经热门股票",
        "url": "https://xueqiu.com/",
        "type": SourceType.API,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://stock.xueqiu.com/v5/stock/hot_stock/list.json?size=30&_type=10&type=10",
            "data_path": "data.items"
        }
    },
    {
        "id": "zaobao",
        "name": "早晨报",
        "description": "早晨报实时新闻",
        "url": "https://www.zaochenbao.com/realtime/",
        "type": SourceType.WEB,
        "category": "news",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "selector": "div.list-block>a.item",
            "title_selector": ".eps",
            "date_selector": ".pdt10",
            "encoding": "gb2312"
        }
    },
    {
        "id": "zhihu",
        "name": "知乎热榜",
        "description": "知乎热门话题",
        "url": "https://www.zhihu.com/",
        "type": SourceType.API,
        "category": "social",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=20&desktop=true",
            "data_path": "data"
        }
    },
    {
        "id": "zhihu_daily",
        "name": "知乎日报",
        "description": "知乎日报精选内容",
        "url": "https://daily.zhihu.com/",
        "type": SourceType.API,
        "category": "knowledge",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "api_url": "https://daily.zhihu.com/api/4/news/latest",
            "backup_urls": ["https://news-at.zhihu.com/api/4/news/latest"]
        }
    },
    {
        "id": "bbc_world",
        "name": "BBC World News",
        "description": "BBC世界新闻",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "type": SourceType.RSS,
        "category": "news",
        "country": "英国",
        "language": "en",
        "config": {
            "backup_urls": [
                "https://news.google.com/rss/search?q=site:bbc.com/news&hl=en-US&gl=US&ceid=US:en"
            ]
        }
    },
    {
        "id": "bloomberg",
        "name": "彭博社",
        "description": "彭博社国际财经新闻",
        "url": "https://news.google.com/rss/search?q=site:bloomberg.com&hl=en-US&gl=US&ceid=US:en",
        "type": SourceType.RSS,
        "category": "finance",
        "country": "美国",
        "language": "en",
        "config": {
            "feed_type": "latest",
            "backup_urls": [
                "https://news.google.com/rss/search?q=site:bloomberg.com+finance&hl=en-US&gl=US&ceid=US:en"
            ]
        }
    },
    {
        "id": "bloomberg-markets",
        "name": "彭博社市场",
        "description": "彭博社市场新闻",
        "url": "https://news.google.com/rss/search?q=site:bloomberg.com+markets&hl=en-US&gl=US&ceid=US:en",
        "type": SourceType.RSS,
        "category": "finance",
        "country": "美国",
        "language": "en",
        "config": {
            "feed_type": "markets"
        }
    },
    {
        "id": "bloomberg-tech",
        "name": "彭博社科技",
        "description": "彭博社科技新闻",
        "url": "https://news.google.com/rss/search?q=site:bloomberg.com+technology&hl=en-US&gl=US&ceid=US:en",
        "type": SourceType.RSS,
        "category": "tech",
        "country": "美国",
        "language": "en",
        "config": {
            "feed_type": "technology"
        }
    },
    {
        "id": "coolapk",
        "name": "酷安",
        "description": "酷安新闻和动态",
        "url": "https://www.coolapk.com",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "third_party_url": "https://api.vvhan.com/api/apptop"
        }
    },
    {
        "id": "coolapk-feed",
        "name": "酷安动态",
        "description": "酷安动态消息",
        "url": "https://www.coolapk.com",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "中国",
        "language": "zh-CN",
        "config": {}
    },
    {
        "id": "coolapk-app",
        "name": "酷安应用",
        "description": "酷安应用更新和推荐",
        "url": "https://www.coolapk.com/apk",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "中国",
        "language": "zh-CN",
        "config": {}
    },
    {
        "id": "cls",
        "name": "财联社",
        "description": "财联社财经新闻",
        "url": "https://www.cls.cn/",
        "type": SourceType.API,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "public_api_url": "https://api.tianapi.com/caijing/index",
            "backup_api_url": "https://api.jisuapi.com/finance/news"
        }
    },
    {
        "id": "yicai-brief",
        "name": "第一财经快讯",
        "description": "第一财经网站快讯",
        "url": "https://www.yicai.com/brief/",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "use_selenium": True,
            "headless": True,
            "selenium_timeout": 15,
            "selenium_wait_time": 3,
            "max_retries": 2,
            "retry_delay": 2,
            "use_cache": True,
            "cache_ttl": 1800,
            "use_random_delay": True,
            "min_delay": 0.5,
            "max_delay": 1.5,
            "overall_timeout": 60,
            "use_http_fallback": True,
            "content_type": "brief"
        }
    },
    {
        "id": "yicai-news",
        "name": "第一财经新闻",
        "description": "第一财经网站新闻",
        "url": "https://www.yicai.com/news/",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "use_selenium": True,
            "headless": True,
            "selenium_timeout": 15,
            "selenium_wait_time": 3,
            "max_retries": 2,
            "retry_delay": 2,
            "use_cache": True,
            "cache_ttl": 1800,
            "use_random_delay": True,
            "min_delay": 0.5,
            "max_delay": 1.5,
            "overall_timeout": 60,
            "use_http_fallback": True,
            "content_type": "news"
        }
    },
    {
        "id": "ifeng-studio",
        "name": "凤凰财经全球快报",
        "description": "凤凰财经工作室全球快报",
        "url": "https://finance.ifeng.com/studio",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "max_retries": 3,
            "retry_delay": 2,
            "use_cache": True,
            "cache_ttl": 900,
            "use_random_delay": True,
            "min_delay": 0.5,
            "max_delay": 1.5,
            "headers": {
                "Referer": "https://www.ifeng.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        }
    },
    {
        "id": "ifeng-tech",
        "name": "凤凰科技",
        "description": "凤凰网科技频道新闻",
        "url": "https://tech.ifeng.com/",
        "type": SourceType.WEB,
        "category": "tech",
        "country": "中国",
        "language": "zh-CN",
        "config": {
            "max_retries": 3,
            "retry_delay": 2,
            "use_cache": True,
            "cache_ttl": 1200,
            "use_random_delay": True,
            "min_delay": 0.5,
            "max_delay": 1.5,
            "headers": {
                "Referer": "https://www.ifeng.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        }
    },
    {
        "id": "custom-nbd",
        "name": "每日经济新闻",
        "description": "Auto-generated source for https://www.nbd.com.cn/",
        "url": "https://www.nbd.com.cn/",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "CN",
        "language": "zh-CN",
        "config": {
            
                "selectors": {
                    "item": ".content.normal-real .kuaiXunBox > .itemBox",
                    "title": ".u-newsText .u-content",
                    "link": "a",
                    "date": ".u-time",
                    "summary": "",
                    "content": ""
                },
                "use_selenium": true,
                "auto_generated": true,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,en-US;q=0.8,en;q=0.5",
                    "Connection": "keep-alive"
                }
        }
    },
    {
        "id": "custom-hexun-roll",
        "name": "和讯滚动新闻",
        "description": "Auto-generated source for https://roll.hexun.com/",
        "url": "https://roll.hexun.com/",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "CN",
        "language": "zh-CN",
        "config": {
            
                "selectors": {
                    "item": "#immeList .ntb > li",
                    "title": "a",
                    "link": "a",
                    "date": "b",
                    "summary": "",
                    "content": ""
                },
                "use_selenium": true,
                "auto_generated": true,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,en-US;q=0.8,en;q=0.5",
                    "Connection": "keep-alive"
                }
        }
    },
    {
        "id": "custom-163hot",
        "name": "网易热点排行",
        "description": "Auto-generated source for https://news.163.com/",
        "url": "https://news.163.com/",
        "type": SourceType.WEB,
        "category": "news",
        "country": "CN",
        "language": "zh-CN",
        "config": {
            
                "selectors": {
                    "item": ".mt35.mod_hot_rank.clearfix.cm_area_show ul > li",
                    "title": "a",
                    "link": "a",
                    "date": "",
                    "summary": "",
                    "content": ""
                },
                "use_selenium": true,
                "auto_generated": true,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,en-US;q=0.8,en;q=0.5",
                    "Connection": "keep-alive"
                }
        }
    },
    {
        "id": "custom-cnstock-flashnews",
        "name": "上海证券报-快讯",
        "description": "Auto-generated source for https://www.cnstock.com/fastNews/10004",
        "url": "https://www.cnstock.com/fastNews/10004",
        "type": SourceType.WEB,
        "category": "finance",
        "country": "CN",
        "language": "zh-CN",
        "config": {
            
                "selectors": {
                    "item": ".ant-timeline .ant-timeline-item",
                    "title": ".ant-timeline .ant-timeline-item p[class*=\"font\"]",
                    "link": ".ant-timeline .ant-timeline-item a[href]",
                    "date": ".ant-timeline .ant-timeline-item [class*=\"ant-timeline\"]",
                    "summary": "",
                    "content": ""
                },
                "use_selenium": true,
                "auto_generated": true,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,en-US;q=0.8,en;q=0.5",
                    "Connection": "keep-alive"
                }
        }
    }
]

# 函数: 确保配置是可JSON序列化的
def ensure_serializable(obj):
    """
    确保对象是可JSON序列化的，移除任何不可序列化的部分
    """
    if isinstance(obj, dict):
        return {k: ensure_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [ensure_serializable(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        # 对于其他类型，尝试转换为字符串
        try:
            # 测试是否可序列化
            json.dumps(obj)
            return obj
        except (TypeError, OverflowError):
            # 如果无法序列化，转换为字符串表示
            return str(obj)

def init_db():
    """初始化数据库中的新闻源数据"""
    db = SessionLocal()
    try:
        # 创建分类
        categories = {}
        for category_id, category_name in CATEGORIES.items():
            # 检查分类是否已存在
            db_category = db.query(Category).filter(Category.slug == category_id).first()
            if not db_category:
                db_category = Category(
                    name=category_name,
                    slug=category_id,
                    description=f"{category_name}分类",
                    order=list(CATEGORIES.keys()).index(category_id)
                )
                db.add(db_category)
                db.commit()
                db.refresh(db_category)
            categories[category_id] = db_category.id
        
        # 创建新闻源
        for source_data in SOURCES:
            # 检查新闻源是否已存在
            db_source = db.query(Source).filter(Source.id == source_data["id"]).first()
            if not db_source:
                # 获取分类ID
                category_id = categories.get(source_data["category"])
                
                # 确保配置是可序列化的
                serializable_config = ensure_serializable(source_data["config"])
                
                # 创建新闻源
                db_source = Source(
                    id=source_data["id"],
                    name=source_data["name"],
                    description=source_data["description"],
                    url=source_data["url"],
                    type=source_data["type"],
                    category_id=category_id,
                    country=source_data["country"],
                    language=source_data["language"],
                    config=serializable_config,
                    status=SourceStatus.ACTIVE,
                    update_interval=datetime.timedelta(minutes=10),
                    cache_ttl=datetime.timedelta(minutes=5),
                    priority=SOURCES.index(source_data)
                )
                db.add(db_source)
                print(f"添加新闻源: {source_data['name']} ({source_data['id']})")
            else:
                print(f"新闻源已存在: {source_data['name']} ({source_data['id']})")
        
        db.commit()
        print("新闻源初始化完成！")
    except Exception as e:
        db.rollback()
        print(f"初始化失败: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db() 