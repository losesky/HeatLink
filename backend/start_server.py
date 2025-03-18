#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HeatLink 后端服务启动脚本

本脚本用于启动HeatLink后端服务，包括以下功能:
1. 自动同步数据库源和源适配器
2. 缓存数据到Redis中
3. 启动API服务

使用方法:
python start_server.py [--sync-only] [--no-cache] [--host HOST] [--port PORT] [--reload]

参数:
--sync-only: 只同步数据库和适配器，不启动服务
--no-cache: 不使用Redis缓存
--host: 服务器监听地址，默认为0.0.0.0
--port: 服务器监听端口，默认为8000
--reload: 启用热重载，开发环境下有用

外部接口将通过Redis缓存获取数据，提高响应速度和性能。
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


class SourceSynchronizer:
    """
    数据库源和源适配器同步器
    """
    
    def __init__(self, verbose=False, cache_manager=None):
        self.verbose = verbose
        self.cache_manager = cache_manager
        self.db = SessionLocal()
        
    def __del__(self):
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
                        "type": self._get_source_type(source)
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
        try:
            result = self.db.execute(text("SELECT id, name, description, url, type, active FROM sources"))
            sources = []
            for row in result:
                sources.append({
                    "id": row[0],
                    "name": row[1],
                    "description": row[2] or '',
                    "url": row[3] or '',
                    "type": row[4],
                    "active": row[5]
                })
            self.log(f"从数据库中获取了 {len(sources)} 个源记录")
            return sources
        except Exception as e:
            self.log(f"从数据库获取源记录失败: {str(e)}", "error")
            return []
    
    def sync_sources(self):
        """同步数据库源和源适配器"""
        self.log("开始同步数据库源和源适配器...")
        
        # 获取代码和数据库中的源
        code_sources = self.get_code_sources()
        db_sources = self.get_db_sources()
        
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
            "mismatch": len(mismatch)
        }
    
    def _fix_missing_in_db(self, missing_sources):
        """添加缺失的源到数据库"""
        if not missing_sources:
            return
        
        self.log(f"正在添加 {len(missing_sources)} 个缺失的源到数据库...")
        
        for source in missing_sources:
            try:
                # 构建插入SQL
                sql = text("""
                INSERT INTO sources (id, name, description, url, type, active, 
                                    update_interval, cache_ttl, status, created_at, updated_at)
                VALUES (:id, :name, :description, :url, :type::sourcetype, true, 
                        interval ':update_interval seconds', interval ':cache_ttl seconds', 
                        'INACTIVE'::sourcestatus, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """)
                
                # 执行插入
                self.db.execute(sql, {
                    "id": source["id"],
                    "name": source["name"],
                    "description": source["description"],
                    "url": source["url"],
                    "type": source["type"],
                    "update_interval": settings.DEFAULT_UPDATE_INTERVAL,
                    "cache_ttl": settings.DEFAULT_CACHE_TTL
                })
                
                self.log(f"已添加源: {source['id']} ({source['name']})")
            except Exception as e:
                self.log(f"添加源 {source['id']} 失败: {str(e)}", "error")
        
        # 提交事务
        self.db.commit()
    
    def _fix_mismatch(self, mismatches):
        """修复属性不匹配的源"""
        if not mismatches:
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
        self.db.commit()
    
    def _update_inactive(self, missing_sources):
        """将代码中缺失的源标记为非活跃"""
        if not missing_sources:
            return
        
        self.log(f"正在将 {len(missing_sources)} 个代码中缺失的源标记为非活跃...")
        
        for source in missing_sources:
            try:
                # 构建更新SQL
                sql = text("""
                UPDATE sources
                SET active = false, updated_at = CURRENT_TIMESTAMP
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
        self.db.commit()
    
    async def _cache_sources_to_redis(self):
        """缓存源信息到Redis"""
        if not self.cache_manager:
            return
        
        self.log("正在缓存源信息到Redis...")
        
        # 准备缓存
        await self.cache_manager.initialize()
        
        try:
            # 获取所有活跃的源
            sql = text("""
            SELECT id, name, description, url, type, country, language, 
                   priority, status
            FROM sources 
            WHERE active = true
            ORDER BY priority DESC, name
            """)
            result = self.db.execute(sql)
            
            sources = []
            for row in result:
                sources.append({
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "url": row[3],
                    "type": row[4],
                    "country": row[5],
                    "language": row[6],
                    "priority": row[7],
                    "status": row[8]
                })
            
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
            
            # 缓存每个源的详细信息
            for source in sources:
                await self.cache_manager.set(f"sources:detail:{source['id']}", source, ttl=3600)
            
            self.log(f"已缓存 {len(sources)} 个源信息到Redis")
            
            # 获取所有源的最新统计信息
            sql = text("""
            SELECT s.source_id, s.success_rate, s.avg_response_time, s.total_requests, s.error_count, s.created_at
            FROM source_stats s
            INNER JOIN (
                SELECT source_id, MAX(created_at) as max_created_at 
                FROM source_stats 
                GROUP BY source_id
            ) latest
            ON s.source_id = latest.source_id AND s.created_at = latest.max_created_at
            """)
            result = self.db.execute(sql)
            
            stats = {}
            for row in result:
                stats[row[0]] = {
                    "source_id": row[0],
                    "success_rate": row[1],
                    "avg_response_time": row[2],
                    "total_requests": row[3],
                    "error_count": row[4],
                    "last_update": row[5].isoformat() if row[5] else None
                }
            
            # 缓存所有统计信息
            await self.cache_manager.set("sources:stats", stats, ttl=300)  # 5分钟过期
            
            self.log(f"已缓存 {len(stats)} 个源统计信息到Redis")
            
        except Exception as e:
            self.log(f"缓存源信息到Redis失败: {str(e)}", "error")
        

async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="HeatLink后端服务启动脚本")
    parser.add_argument("--sync-only", action="store_true", help="只同步数据库和适配器，不启动服务")
    parser.add_argument("--no-cache", action="store_true", help="不使用Redis缓存")
    parser.add_argument("--host", default="0.0.0.0", help="服务器监听地址，默认为0.0.0.0")
    parser.add_argument("--port", type=int, default=8000, help="服务器监听端口，默认为8000")
    parser.add_argument("--reload", action="store_true", help="启用热重载，开发环境下有用")
    args = parser.parse_args()
    
    # 初始化缓存管理器
    cache_manager = None
    if not args.no_cache:
        cache_manager = CacheManager(
            redis_url=settings.REDIS_URL,
            enable_memory_cache=True,
            default_ttl=settings.DEFAULT_CACHE_TTL
        )
        await cache_manager.initialize()
    
    # 创建源同步器
    synchronizer = SourceSynchronizer(verbose=True, cache_manager=cache_manager)
    
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
    
    # 启动后端API服务
    logger.info(f"启动HeatLink后端API服务，地址: {args.host}:{args.port}...")
    
    # 使用uvicorn启动服务
    config = uvicorn.Config(
        "main:app", 
        host=args.host, 
        port=args.port,
        reload=args.reload,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main()) 