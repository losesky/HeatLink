#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HeatLink 后端服务启动脚本

本脚本用于启动HeatLink后端服务，包括以下功能:
1. 自动同步数据库源和源适配器
2. 缓存数据到Redis中
3. 启动API服务

使用方法:
python start_server.py [--sync-only] [--no-cache] [--host HOST] [--port PORT] [--reload] [--fallback-mode] [--verbose-logging]

参数:
--sync-only: 只同步数据库和适配器，不启动服务
--no-cache: 不使用Redis缓存
--host: 服务器监听地址，默认为0.0.0.0
--port: 服务器监听端口，默认为8000
--reload: 启用热重载，开发环境下有用
--fallback-mode: 强制使用本地源适配器数据，不连接数据库和缓存
--verbose-logging: 启用详细日志输出，包括缓存操作

外部接口将通过Redis缓存获取数据，提高响应速度和性能。
当数据库或缓存连接失败时，系统将自动切换到本地源适配器模式运行。
"""

import os
import sys
import argparse
import asyncio
import logging
import signal
import json
import time
from datetime import datetime, timedelta
import uvicorn

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 导入dotenv加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入日志配置
from app.core.logging_config import configure_logging, get_logger

# 配置日志
configure_logging()
logger = get_logger("heatlink_server")

# 导入所需模块
from app.core.config import settings
from app.db.session import SessionLocal
from sqlalchemy import text
from worker.sources.factory import NewsSourceFactory
from worker.cache import CacheManager


class LocalSourceManager:
    """
    本地源适配器管理器
    在数据库或缓存连接失败时提供本地源数据
    """
    
    def __init__(self, cache_manager=None):
        self.cache_manager = cache_manager
        self.factory = NewsSourceFactory()
        self.local_sources = None
        
        # 源分类映射
        self.categories_map = {
            "news": "新闻资讯",
            "tech": "科技",
            "finance": "财经",
            "social": "社交媒体",
            "forum": "论坛社区",
            "dev": "开发者",
            "knowledge": "知识"
        }
        
        # 源类型到分类的映射
        self.type_to_category = {
            "API": "social",
            "WEB": "news",
            "RSS": "news"
        }
        
        # 关键字到分类的映射
        self.keyword_to_category = {
            "zhihu": "knowledge",
            "daily": "news",
            "weibo": "social",
            "baidu": "social",
            "search": "social",
            "hot": "social",
            "news": "news",
            "paper": "news",
            "hacker": "dev",
            "github": "dev",
            "trending": "dev",
            "tech": "tech",
            "technology": "tech",
            "bilibili": "social",
            "video": "social",
            "tube": "social",
            "finance": "finance",
            "economic": "finance",
            "stock": "finance",
            "market": "finance",
            "money": "finance",
            "crypto": "finance",
            "blockchain": "finance",
            "xueqiu": "finance",
            "wallstreet": "finance",
            "bull": "finance",
            "v2ex": "forum",
            "forum": "forum",
            "community": "forum",
            "tieba": "forum",
            "coolapk": "tech",
            "android": "tech",
            "linux": "tech",
            "bloomberg": "finance"
        }
        
    def get_local_sources(self):
        """获取本地源适配器数据"""
        if self.local_sources is not None:
            return self.local_sources
            
        sources = []
        source_types = self.factory.get_available_sources()
        logger.info(f"从本地代码中获取了 {len(source_types)} 个源适配器")
        
        for source_type in source_types:
            try:
                source = self.factory.create_source(source_type)
                if source:
                    # 确定源的分类
                    category = self._guess_category_for_source(source_type, source)
                    
                    sources.append({
                        "id": source_type,
                        "name": source.name,
                        "description": getattr(source, 'description', ''),
                        "url": getattr(source, 'url', ''),
                        "type": self._get_source_type(source),
                        "country": getattr(source, 'country', 'GLOBAL'),
                        "language": getattr(source, 'language', 'zh-CN'),
                        "priority": 1,
                        "status": "ACTIVE",
                        "category_slug": category,
                        "category_name": self.categories_map.get(category, "新闻资讯")
                    })
            except Exception as e:
                logger.warning(f"无法创建源 {source_type}: {str(e)}")
                
        self.local_sources = sources
        return sources
        
    def _get_source_type(self, source):
        """获取源的类型"""
        if hasattr(source, 'source_type'):
            return source.source_type
        
        # 根据类名推断类型
        class_name = source.__class__.__name__.lower()
        if "rss" in class_name:
            return "RSS"
        elif "api" in class_name:
            return "API"
        else:
            return "WEB"
            
    def _guess_category_for_source(self, source_id, source):
        """根据源信息猜测适合的分类"""
        source_id = source_id.lower()
        source_name = source.name.lower()
        source_type = self._get_source_type(source)
        
        # 1. 如果源有自己的分类信息，优先使用
        if hasattr(source, 'category') and source.category:
            return source.category
            
        # 2. 根据源ID和名称中的关键词匹配
        for keyword, category in self.keyword_to_category.items():
            if keyword in source_id or keyword in source_name:
                return category
                
        # 3. 根据源类型判断
        if source_type in self.type_to_category:
            return self.type_to_category[source_type]
            
        # 4. 默认返回新闻分类
        return "news"
            
    async def cache_local_sources(self):
        """将本地源数据缓存到Redis"""
        if not self.cache_manager:
            return
            
        logger.info("正在缓存本地源信息到Redis...")
        
        try:
            await self.cache_manager.initialize()
            sources = self.get_local_sources()
            
            # 按类型分组
            sources_by_type = {}
            for source in sources:
                source_type = source["type"]
                if source_type not in sources_by_type:
                    sources_by_type[source_type] = []
                sources_by_type[source_type].append(source)
                
            # 按分类分组
            sources_by_category = {}
            for source in sources:
                category_slug = source["category_slug"]
                if category_slug not in sources_by_category:
                    sources_by_category[category_slug] = []
                sources_by_category[category_slug].append(source)
            
            # 缓存所有源列表
            await self.cache_manager.set("sources:all", sources, ttl=3600)  # 1小时过期
            
            # 缓存源类型列表
            source_types = list(sources_by_type.keys())
            await self.cache_manager.set("sources:types", source_types, ttl=3600)
            
            # 缓存每种类型的源列表
            for source_type, type_sources in sources_by_type.items():
                await self.cache_manager.set(f"sources:type:{source_type}", type_sources, ttl=3600)
                
            # 缓存分类列表
            category_slugs = list(sources_by_category.keys())
            await self.cache_manager.set("sources:categories", category_slugs, ttl=3600)
            
            # 缓存每个分类的源列表
            for category_slug, category_sources in sources_by_category.items():
                await self.cache_manager.set(f"sources:category:{category_slug}", category_sources, ttl=3600)
            
            # 缓存每个源的详细信息
            for source in sources:
                await self.cache_manager.set(f"sources:detail:{source['id']}", source, ttl=3600)
                
            # 缓存空的统计信息，避免前端获取失败
            await self.cache_manager.set("sources:stats", {}, ttl=300)
            
            # 记录缺少统计信息的源
            logger.warning(f"本地回退模式下所有 {len(sources)} 个源都没有统计信息")
            
            # 缓存分类信息
            categories = []
            for slug, name in self.categories_map.items():
                categories.append({
                    "id": slug,
                    "name": name,
                    "slug": slug,
                    "description": f"{name}分类"
                })
            await self.cache_manager.set("categories:all", categories, ttl=3600)
            
            logger.info(f"已缓存 {len(sources)} 个本地源信息和 {len(categories)} 个分类到Redis")
            
        except Exception as e:
            logger.error(f"缓存本地源信息到Redis失败: {str(e)}")


class SourceSynchronizer:
    """
    数据库源和源适配器同步器
    """
    
    def __init__(self, verbose=False, cache_manager=None, fallback_mode=False):
        self.verbose = verbose
        self.cache_manager = cache_manager
        self.fallback_mode = fallback_mode
        self.db = None
        self.db_available = False
        
        # 如果不是强制回退模式，尝试连接数据库
        if not self.fallback_mode:
            try:
                self.db = SessionLocal()
                # 测试连接是否有效
                self.db.execute(text("SELECT 1"))
                self.db_available = True
                logger.info("数据库连接成功")
            except Exception as e:
                logger.error(f"数据库连接失败: {str(e)}")
                logger.warning("将使用本地源适配器数据运行")
                self.db_available = False
                self.fallback_mode = True
        
        # 创建本地源管理器
        self.local_manager = LocalSourceManager(cache_manager)
        
        # 源分类映射
        self.categories_map = {
            "news": "新闻资讯",
            "tech": "科技",
            "finance": "财经",
            "social": "社交媒体",
            "forum": "论坛社区",
            "dev": "开发者",
            "knowledge": "知识"
        }
        
        # 源类型到分类的映射
        self.type_to_category = {
            "API": "social",
            "WEB": "news",
            "RSS": "news"
        }
        
        # 关键字到分类的映射
        self.keyword_to_category = {
            "zhihu": "knowledge",
            "daily": "news",
            "weibo": "social",
            "baidu": "social",
            "search": "social",
            "hot": "social",
            "news": "news",
            "paper": "news",
            "hacker": "dev",
            "github": "dev",
            "trending": "dev",
            "tech": "tech",
            "technology": "tech",
            "bilibili": "social",
            "video": "social",
            "tube": "social",
            "finance": "finance",
            "economic": "finance",
            "stock": "finance",
            "market": "finance",
            "money": "finance",
            "crypto": "finance",
            "blockchain": "finance",
            "xueqiu": "finance",
            "wallstreet": "finance",
            "bull": "finance",
            "v2ex": "forum",
            "forum": "forum",
            "community": "forum",
            "tieba": "forum",
            "coolapk": "tech",
            "android": "tech",
            "linux": "tech",
            "bloomberg": "finance"
        }
        
    def __del__(self):
        if self.db:
            self.db.close()
    
    def log(self, message, level="info"):
        """记录日志"""
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        elif level == "debug" and self.verbose:
            logger.debug(message)
    
    def get_code_sources(self):
        """获取代码中定义的所有源适配器"""
        factory = NewsSourceFactory()
        sources = []
        
        # 获取所有定义的源类型
        source_types = factory.get_available_sources()
        self.log(f"从代码中获取了 {len(source_types)} 个源适配器")
        
        for source_type in source_types:
            try:
                # 创建源实例以获取元数据
                source = factory.create_source(source_type)
                if source:
                    sources.append({
                        "id": source_type,
                        "name": source.name,
                        "description": getattr(source, 'description', ''),
                        "url": getattr(source, 'url', ''),
                        "type": self._get_source_type(source),
                        "category": getattr(source, 'category', None)
                    })
            except Exception as e:
                self.log(f"无法创建源 {source_type}: {str(e)}", "warning")
        
        return sources
    
    def _get_source_type(self, source):
        """获取源的类型"""
        if hasattr(source, 'source_type'):
            return source.source_type
        
        # 根据类名推断类型
        class_name = source.__class__.__name__.lower()
        if "rss" in class_name:
            return "RSS"
        elif "api" in class_name:
            return "API"
        else:
            return "WEB"
            
    def get_db_sources(self):
        """获取数据库中的所有源记录"""
        if not self.db_available:
            return []
            
        try:
            result = self.db.execute(text("SELECT id, name, description, url, type, status, category_id FROM sources"))
            sources = []
            for row in result:
                sources.append({
                    "id": row[0],
                    "name": row[1],
                    "description": row[2] or '',
                    "url": row[3] or '',
                    "type": row[4],
                    "status": row[5],
                    "category_id": row[6]
                })
            self.log(f"从数据库中获取了 {len(sources)} 个源记录")
            return sources
        except Exception as e:
            self.log(f"从数据库获取源记录失败: {str(e)}", "error")
            self.db_available = False
            self.fallback_mode = True
            return []
    
    def get_category_mapping(self):
        """获取分类ID映射"""
        if not self.db_available:
            return {}
            
        try:
            result = self.db.execute(text("SELECT id, slug FROM categories"))
            categories = {}
            for row in result:
                categories[row[1]] = row[0]
            self.log(f"从数据库中获取了 {len(categories)} 个分类映射")
            return categories
        except Exception as e:
            self.log(f"从数据库获取分类映射失败: {str(e)}", "error")
            return {}
            
    def guess_category_for_source(self, source):
        """根据源信息猜测适合的分类"""
        source_id = source["id"].lower()
        source_name = source["name"].lower()
        source_type = source["type"]
        
        # 1. 如果源有自己的分类信息，优先使用
        if "category" in source and source["category"]:
            return source["category"]
            
        # 2. 根据源ID和名称中的关键词匹配
        for keyword, category in self.keyword_to_category.items():
            if keyword in source_id or keyword in source_name:
                return category
                
        # 3. 根据源类型判断
        if source_type in self.type_to_category:
            return self.type_to_category[source_type]
            
        # 4. 默认返回新闻分类
        return "news"
        
    def ensure_categories_exist(self):
        """确保所有必要的分类存在"""
        if not self.db_available:
            return
            
        try:
            # 获取现有分类
            categories = self.get_category_mapping()
            
            # 创建缺失的分类
            for slug, name in self.categories_map.items():
                if slug not in categories:
                    self.log(f"创建缺失的分类: {name} ({slug})")
                    
                    # 构建插入SQL
                    sql = text("""
                    INSERT INTO categories (name, slug, description, created_at, updated_at)
                    VALUES (:name, :slug, :description, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                    """)
                    
                    # 执行插入
                    result = self.db.execute(sql, {
                        "name": name,
                        "slug": slug,
                        "description": f"{name}分类"
                    })
                    
                    # 获取新插入的ID
                    category_id = result.fetchone()[0]
                    categories[slug] = category_id
                    
                    # 提交事务
                    self.db.commit()
            
            return categories
        except Exception as e:
            self.log(f"确保分类存在失败: {str(e)}", "error")
            self.db.rollback()
            return {}
    
    def fix_missing_categories(self):
        """修复缺失的分类ID"""
        if not self.db_available:
            return
            
        try:
            # 确保所有分类存在
            categories = self.ensure_categories_exist()
            if not categories:
                self.log("无法获取分类信息，跳过修复分类", "warning")
                return
                
            # 获取所有没有分类的源
            result = self.db.execute(text("SELECT id, name, type FROM sources WHERE category_id IS NULL"))
            sources_without_category = []
            for row in result:
                sources_without_category.append({
                    "id": row[0],
                    "name": row[1],
                    "type": row[2]
                })
                
            if not sources_without_category:
                self.log("所有源都已分配分类，无需修复")
                return
                
            self.log(f"发现 {len(sources_without_category)} 个缺少分类的源")
            
            # 为每个源猜测并分配分类
            for source in sources_without_category:
                # 猜测分类
                category_slug = self.guess_category_for_source(source)
                if category_slug not in categories:
                    self.log(f"无法找到分类 {category_slug}，使用默认分类 'news'")
                    category_slug = "news"
                    
                category_id = categories[category_slug]
                
                # 更新源的分类ID
                sql = text("""
                UPDATE sources
                SET category_id = :category_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """)
                
                self.db.execute(sql, {
                    "id": source["id"],
                    "category_id": category_id
                })
                
                self.log(f"已为源 {source['id']} ({source['name']}) 分配分类: {category_slug}")
            
            # 提交事务
            self.db.commit()
            self.log("分类修复完成")
            
        except Exception as e:
            self.log(f"修复分类失败: {str(e)}", "error")
            self.db.rollback()
            
    def sync_sources(self):
        """同步数据库源和源适配器"""
        self.log("开始同步数据库源和源适配器...")
        
        # 如果处于回退模式，使用本地源数据
        if self.fallback_mode:
            self.log("系统处于回退模式，将使用本地源适配器数据")
            if self.cache_manager:
                asyncio.create_task(self.local_manager.cache_local_sources())
            return {
                "total_code_sources": len(self.local_manager.get_local_sources()),
                "total_db_sources": 0,
                "missing_in_db": 0,
                "missing_in_code": 0,
                "mismatch": 0,
                "fallback_mode": True
            }
        
        # 获取代码和数据库中的源
        code_sources = self.get_code_sources()
        db_sources = self.get_db_sources()
        
        # 如果数据库连接失败，切换到回退模式
        if not self.db_available:
            self.log("数据库连接失败，切换到回退模式")
            self.fallback_mode = True
            if self.cache_manager:
                asyncio.create_task(self.local_manager.cache_local_sources())
            return {
                "total_code_sources": len(code_sources),
                "total_db_sources": 0,
                "missing_in_db": 0,
                "missing_in_code": 0,
                "mismatch": 0,
                "fallback_mode": True
            }
        
        # 修复缺失的分类ID
        self.fix_missing_categories()
        
        # 映射为字典，方便查找
        code_sources_dict = {s["id"]: s for s in code_sources}
        db_sources_dict = {s["id"]: s for s in db_sources}
        
        # 1. 找出代码中有但数据库中没有的源
        missing_in_db = []
        for source_id, source in code_sources_dict.items():
            if source_id not in db_sources_dict:
                missing_in_db.append(source)
        
        # 2. 找出数据库中有但代码中没有的源
        missing_in_code = []
        for source_id, source in db_sources_dict.items():
            if source_id not in code_sources_dict and source_id != "rss":  # 排除通用rss源
                missing_in_code.append(source)
        
        # 3. 找出属性不匹配的源
        mismatch = []
        for source_id, code_source in code_sources_dict.items():
            if source_id in db_sources_dict:
                db_source = db_sources_dict[source_id]
                if code_source["name"] != db_source["name"] or \
                   code_source["url"] != db_source["url"] or \
                   code_source["type"] != db_source["type"]:
                    mismatch.append({
                        "code": code_source,
                        "db": db_source
                    })
        
        # 输出同步报告
        self.log(f"同步报告:")
        self.log(f"- 代码中有 {len(code_sources)} 个源适配器")
        self.log(f"- 数据库中有 {len(db_sources)} 个源记录")
        self.log(f"- 需要添加到数据库的源: {len(missing_in_db)}")
        self.log(f"- 代码中缺失的源: {len(missing_in_code)}")
        self.log(f"- 属性不匹配的源: {len(mismatch)}")
        
        # 自动修复
        self._fix_missing_in_db(missing_in_db)
        self._fix_mismatch(mismatch)
        self._update_inactive(missing_in_code)
        
        # 缓存源信息到Redis
        if self.cache_manager:
            asyncio.create_task(self._cache_sources_to_redis())
        
        self.log("同步完成")
        return {
            "total_code_sources": len(code_sources),
            "total_db_sources": len(db_sources),
            "missing_in_db": len(missing_in_db),
            "missing_in_code": len(missing_in_code),
            "mismatch": len(mismatch),
            "fallback_mode": False
        }
    
    def _fix_missing_in_db(self, missing_sources):
        """添加缺失的源到数据库"""
        if not missing_sources or not self.db_available:
            return
            
        # 确保所有分类存在
        categories = self.ensure_categories_exist()
        if not categories:
            self.log("无法获取分类信息，跳过添加源", "warning")
            return
        
        self.log(f"正在添加 {len(missing_sources)} 个缺失的源到数据库...")
        
        for source in missing_sources:
            try:
                # 猜测分类
                category_slug = self.guess_category_for_source(source)
                if category_slug not in categories:
                    category_slug = "news"  # 默认使用新闻分类
                    
                category_id = categories[category_slug]
                
                # 构建插入SQL
                sql = text("""
                INSERT INTO sources (id, name, description, url, type, active, 
                                    update_interval, cache_ttl, status, category_id, created_at, updated_at)
                VALUES (:id, :name, :description, :url, :type::sourcetype, true, 
                        interval ':update_interval seconds', interval ':cache_ttl seconds', 
                        'INACTIVE'::sourcestatus, :category_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """)
                
                # 执行插入
                self.db.execute(sql, {
                    "id": source["id"],
                    "name": source["name"],
                    "description": source["description"],
                    "url": source["url"],
                    "type": source["type"],
                    "update_interval": settings.DEFAULT_UPDATE_INTERVAL,
                    "cache_ttl": settings.DEFAULT_CACHE_TTL,
                    "category_id": category_id
                })
                
                self.log(f"已添加源: {source['id']} ({source['name']}), 分类: {category_slug}")
            except Exception as e:
                self.log(f"添加源 {source['id']} 失败: {str(e)}", "error")
        
        # 提交事务
        try:
            self.db.commit()
        except Exception as e:
            self.log(f"提交事务失败: {str(e)}", "error")
            self.db_available = False
            self.fallback_mode = True
    
    def _fix_mismatch(self, mismatches):
        """修复属性不匹配的源"""
        if not mismatches or not self.db_available:
            return
        
        self.log(f"正在修复 {len(mismatches)} 个属性不匹配的源...")
        
        for item in mismatches:
            code_source = item["code"]
            db_source = item["db"]
            try:
                # 构建更新SQL
                sql = text("""
                UPDATE sources
                SET name = :name, description = :description, url = :url, type = :type,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """)
                
                # 执行更新
                self.db.execute(sql, {
                    "id": code_source["id"],
                    "name": code_source["name"],
                    "description": code_source["description"],
                    "url": code_source["url"],
                    "type": code_source["type"]
                })
                
                self.log(f"已更新源: {code_source['id']} ({code_source['name']})")
            except Exception as e:
                self.log(f"更新源 {code_source['id']} 失败: {str(e)}", "error")
        
        # 提交事务
        try:
            self.db.commit()
        except Exception as e:
            self.log(f"提交事务失败: {str(e)}", "error")
            self.db_available = False
            self.fallback_mode = True
    
    def _update_inactive(self, missing_sources):
        """将代码中缺失的源标记为非活跃"""
        if not missing_sources or not self.db_available:
            return
        
        self.log(f"正在将 {len(missing_sources)} 个代码中缺失的源标记为非活跃...")
        
        for source in missing_sources:
            try:
                # 构建更新SQL
                sql = text("""
                UPDATE sources
                SET status = 'INACTIVE', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """)
                
                # 执行更新
                self.db.execute(sql, {
                    "id": source["id"]
                })
                
                self.log(f"已将源标记为非活跃: {source['id']} ({source['name']})")
            except Exception as e:
                self.log(f"更新源 {source['id']} 状态失败: {str(e)}", "error")
        
        # 提交事务
        try:
            self.db.commit()
        except Exception as e:
            self.log(f"提交事务失败: {str(e)}", "error")
            self.db_available = False
            self.fallback_mode = True
    
    async def _cache_sources_to_redis(self):
        """缓存源信息到Redis"""
        if not self.cache_manager:
            return
            
        if self.fallback_mode:
            # 在回退模式下使用本地源数据
            await self.local_manager.cache_local_sources()
            return
        
        self.log("正在缓存源信息到Redis...")
        
        # 准备缓存
        await self.cache_manager.initialize()
        
        try:
            # 获取所有活跃的源
            sql = text("""
            SELECT s.id, s.name, s.description, s.url, s.type, s.country, s.language, 
                   s.priority, s.status, s.category_id, c.name as category_name, c.slug as category_slug
            FROM sources s
            LEFT JOIN categories c ON s.category_id = c.id
            WHERE s.status = 'ACTIVE'
            ORDER BY s.priority DESC, s.name
            """)
            result = self.db.execute(sql)
            
            sources = []
            sources_by_category = {}
            
            for row in result:
                source_info = {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "url": row[3],
                    "type": row[4],
                    "country": row[5],
                    "language": row[6],
                    "priority": row[7],
                    "status": row[8],
                    "category_id": row[9]
                }
                
                # 添加分类信息
                if row[9]:  # 如果有分类ID
                    source_info["category_name"] = row[10]
                    source_info["category_slug"] = row[11]
                
                sources.append(source_info)
                
                # 按分类组织源
                category_slug = row[11] if row[11] else "uncategorized"
                if category_slug not in sources_by_category:
                    sources_by_category[category_slug] = []
                sources_by_category[category_slug].append(source_info)
            
            # 按类型分组
            sources_by_type = {}
            for source in sources:
                source_type = source["type"]
                if source_type not in sources_by_type:
                    sources_by_type[source_type] = []
                sources_by_type[source_type].append(source)
            
            # 缓存所有源列表
            await self.cache_manager.set("sources:all", sources, ttl=3600)  # 1小时过期
            
            # 缓存源类型列表
            source_types = list(sources_by_type.keys())
            await self.cache_manager.set("sources:types", source_types, ttl=3600)
            
            # 缓存每种类型的源列表
            for source_type, type_sources in sources_by_type.items():
                await self.cache_manager.set(f"sources:type:{source_type}", type_sources, ttl=3600)
                
            # 缓存分类列表
            category_slugs = list(sources_by_category.keys())
            await self.cache_manager.set("sources:categories", category_slugs, ttl=3600)
            
            # 缓存每个分类的源列表
            for category_slug, category_sources in sources_by_category.items():
                await self.cache_manager.set(f"sources:category:{category_slug}", category_sources, ttl=3600)
            
            # 缓存每个源的详细信息
            for source in sources:
                await self.cache_manager.set(f"sources:detail:{source['id']}", source, ttl=3600)
            
            self.log(f"已缓存 {len(sources)} 个源信息到Redis")
            
            # 获取所有源的最新统计信息
            sql = text("""
            SELECT sources.id as source_id, 
                   COALESCE(ss.success_rate, 0) as success_rate, 
                   COALESCE(ss.avg_response_time, 0) as avg_response_time, 
                   COALESCE(ss.total_requests, 0) as total_requests, 
                   COALESCE(ss.error_count, 0) as error_count, 
                   ss.created_at
            FROM sources
            LEFT JOIN (
                SELECT s.source_id, s.success_rate, s.avg_response_time, s.total_requests, s.error_count, s.created_at
                FROM source_stats s
                INNER JOIN (
                    SELECT source_id, MAX(created_at) as max_created_at 
                    FROM source_stats 
                    GROUP BY source_id
                ) latest
                ON s.source_id = latest.source_id AND s.created_at = latest.max_created_at
            ) ss ON sources.id = ss.source_id
            WHERE sources.status = 'ACTIVE'
            """)
            result = self.db.execute(sql)
            
            stats = {}
            sources_with_stats = 0
            sources_without_stats = 0
            
            for row in result:
                source_id = row[0]
                has_stats = row[5] is not None  # 检查created_at是否为None来判断是否有统计记录
                
                stats[source_id] = {
                    "source_id": source_id,
                    "success_rate": row[1],
                    "avg_response_time": row[2],
                    "total_requests": row[3],
                    "error_count": row[4],
                    "last_update": row[5].isoformat() if row[5] else None,
                    "has_stats": has_stats
                }
                
                if has_stats:
                    sources_with_stats += 1
                else:
                    sources_without_stats += 1
            
            # 缓存所有统计信息
            await self.cache_manager.set("sources:stats", stats, ttl=300)  # 5分钟过期
            
            self.log(f"已缓存 {len(stats)} 个源统计信息到Redis（有统计数据：{sources_with_stats}，无统计数据：{sources_without_stats}）")
            
            # 检查哪些源缺少统计信息
            missing_stats_sources = []
            for source_id, stat in stats.items():
                if not stat.get("has_stats", False):
                    source_name = next((s["name"] for s in sources if s["id"] == source_id), source_id)
                    missing_stats_sources.append(f"{source_id}({source_name})")
            
            if missing_stats_sources:
                self.log(f"发现 {len(missing_stats_sources)} 个源缺少统计信息: {', '.join(missing_stats_sources)}", "warning")
            else:
                self.log("所有源都有对应的统计信息", "info")
            
        except Exception as e:
            self.log(f"缓存源信息到Redis失败: {str(e)}", "error")
            # 如果缓存失败，使用本地源数据
            await self.local_manager.cache_local_sources()
        

async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="HeatLink后端服务启动脚本")
    parser.add_argument("--sync-only", action="store_true", help="只同步数据库和适配器，不启动服务")
    parser.add_argument("--no-cache", action="store_true", help="不使用Redis缓存")
    parser.add_argument("--host", default="0.0.0.0", help="服务器监听地址，默认为0.0.0.0")
    parser.add_argument("--port", type=int, default=8000, help="服务器监听端口，默认为8000")
    parser.add_argument("--reload", action="store_true", help="启用热重载，开发环境下有用")
    parser.add_argument("--fallback-mode", action="store_true", help="强制使用本地源适配器数据，不连接数据库和缓存")
    parser.add_argument("--verbose-logging", action="store_true", help="启用详细日志输出，包括缓存操作")
    args = parser.parse_args()
    
    # 配置日志级别
    if not args.verbose_logging:
        # 提高缓存模块的日志级别，减少DEBUG信息
        logging.getLogger('worker.cache').setLevel(logging.INFO)
    
    # 初始化缓存管理器
    cache_manager = None
    if not args.no_cache and not args.fallback_mode:
        try:
            cache_manager = CacheManager(
                redis_url=settings.REDIS_URL,
                enable_memory_cache=True,
                default_ttl=settings.DEFAULT_CACHE_TTL,
                verbose_logging=args.verbose_logging
            )
            await cache_manager.initialize()
            logger.info("Redis缓存连接成功")
        except Exception as e:
            logger.error(f"Redis缓存连接失败: {str(e)}")
            logger.warning("将使用内存缓存运行")
            # 使用内存缓存作为备选
            cache_manager = CacheManager(
                redis_url=None,
                enable_memory_cache=True,
                default_ttl=settings.DEFAULT_CACHE_TTL,
                verbose_logging=args.verbose_logging
            )
            await cache_manager.initialize()
    elif not args.no_cache and args.fallback_mode:
        # 在回退模式下使用内存缓存
        logger.info("使用回退模式，仅启用内存缓存")
        cache_manager = CacheManager(
            redis_url=None,
            enable_memory_cache=True,
            default_ttl=settings.DEFAULT_CACHE_TTL,
            verbose_logging=args.verbose_logging
        )
        await cache_manager.initialize()
    
    # 创建源同步器
    synchronizer = SourceSynchronizer(verbose=True, cache_manager=cache_manager, fallback_mode=args.fallback_mode)
    
    # 同步源
    sync_result = synchronizer.sync_sources()
    
    # 如果只同步不启动服务，则退出
    if args.sync_only:
        if cache_manager:
            await cache_manager.close()
        return
    
    # 设置SIGTERM信号处理，优雅关闭
    def handle_exit(signum, frame):
        logger.info("接收到退出信号，正在关闭服务...")
        if cache_manager:
            asyncio.create_task(cache_manager.close())
        # 给异步任务一些时间完成
        time.sleep(1)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # 设置环境变量，告知应用运行模式
    if synchronizer.fallback_mode:
        os.environ["HEATLINK_FALLBACK_MODE"] = "true"
        logger.info("系统设置为回退模式运行，仅使用本地源适配器数据")
    
    # 启动后端API服务
    logger.info(f"启动HeatLink后端API服务，地址: {args.host}:{args.port}...")
    
    # 使用uvicorn启动服务
    config = uvicorn.Config(
        "main:app", 
        host=args.host, 
        port=args.port,
        reload=args.reload,
        log_level="info",
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "fastapi": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "app": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "worker": {"handlers": ["default"], "level": "INFO", "propagate": False},
            },
        }
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main()) 