#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import asyncio
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

# 添加项目根目录到系统路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

# 导入项目相关模块
try:
    from backend.app.settings import settings
except ImportError:
    # 如果无法导入，设置默认值
    settings = type('Settings', (), {'redis_url': os.environ.get("REDIS_URL", "redis://localhost:6379/0")})
    logging.warning("无法导入backend.app.settings，使用默认值")

# 使用项目中现有的CacheManager
from backend.worker.cache import CacheManager

# 导入NewsSourceManager（如果存在）或使用参考cache_monitor.py中的源管理方式
try:
    from backend.worker.sources.provider import DefaultNewsSourceProvider
    from backend.worker.sources.base import NewsSource
except ImportError:
    # 如果无法导入，参考cache_monitor.py设置默认值
    logging.warning("无法导入NewsSourceProvider，使用简化版本")
    
    class NewsSource:
        def __init__(self, source_id, name):
            self.source_id = source_id
            self.id = source_id  # 兼容性
            self.name = name
            self.cache_ttl = 900
            self.update_interval = 3600

    class DefaultNewsSourceProvider:
        def __init__(self):
            self.sources = [
                NewsSource("example1", "示例源1"),
                NewsSource("example2", "示例源2")
            ]
        
        def get_all_sources(self):
            return self.sources
            
        def get_source(self, source_id):
            for source in self.sources:
                if source.source_id == source_id:
                    return source
            return None

# 导入NewsItemModel或使用简化版实现
try:
    from backend.worker.models import NewsItemModel
except ImportError:
    # 如果无法导入，创建一个简单的模拟类
    logging.warning("无法导入NewsItemModel，使用简化版本")
    class NewsItemModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
        
        def dict(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

# 导入Redis和Jinja2
import redis
try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    logging.error("无法导入jinja2，HTML报告功能将无法使用")

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("RedisCacheMonitor")

# 常量定义
SOURCE_CACHE_PREFIX = "source:"
DEFAULT_TIMEOUT = 30  # 秒

# 导入或创建AdaptiveScheduler
try:
    from backend.worker.scheduler import AdaptiveScheduler
except ImportError:
    # 如果无法导入，参考cache_monitor.py创建简化版本
    class AdaptiveScheduler:
        def __init__(self, source_provider, cache_manager=None):
            self.source_provider = source_provider
            self.cache_manager = cache_manager
            self.sources = {}
        
        async def initialize(self):
            self.sources = {s.source_id: s for s in self.source_provider.get_all_sources()}
            logger.info(f"调度器初始化了 {len(self.sources)} 个源")
        
        async def close(self):
            pass
        
        async def fetch_source(self, source_id, force=False):
            source = self.source_provider.get_source(source_id)
            if not source:
                return False
            logger.info(f"模拟获取源 {source_id} 的新闻")
            return True
        
        def get_all_sources(self):
            return list(self.sources.values())
        
        def get_source(self, source_id):
            return self.sources.get(source_id)

class RedisCacheMonitor:
    """Redis缓存监控工具"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL") or getattr(settings, 'redis_url', "redis://localhost:6379/0")
        self.cache_manager = None
        self.source_provider = None
        self.scheduler = None
        self.initialized = False
    
    async def initialize(self):
        """初始化缓存管理器和源管理器"""
        if self.initialized:
            return
            
        logger.info(f"使用Redis URL: {self.redis_url}")
        
        # 使用项目中现有的CacheManager
        self.cache_manager = CacheManager(
            redis_url=self.redis_url,
            enable_memory_cache=True,
            verbose_logging=True
        )
        await self.cache_manager.initialize()
        
        # 创建源提供者
        self.source_provider = DefaultNewsSourceProvider()
        
        # 创建调度器
        self.scheduler = AdaptiveScheduler(self.source_provider, self.cache_manager)
        await self.scheduler.initialize()
        
        self.initialized = True
        logger.info("初始化完成")
    
    async def cleanup(self):
        """清理资源"""
        if self.cache_manager:
            await self.cache_manager.close()
        logger.info("资源已清理")
    
    async def test_news_source_cache(self, source_id: str, refresh: bool = False) -> bool:
        """测试特定新闻源的缓存是否正常工作"""
        await self.initialize()
        
        # 获取新闻源
        source = self.source_provider.get_source(source_id)
        if not source:
            logger.error(f"找不到新闻源: {source_id}")
            return False
            
        logger.info(f"正在测试新闻源 '{source.name}' ({source_id}) 的缓存...")
        
        # 如果需要刷新，先清除缓存
        if refresh:
            logger.info(f"刷新缓存...")
            cache_key = f"{SOURCE_CACHE_PREFIX}{source_id}"
            await self.cache_manager.delete(cache_key)
        
        # 测试缓存
        try:
            # 获取新闻，触发缓存写入
            logger.info(f"获取新闻数据...")
            await self.scheduler.fetch_source(source_id, force=refresh)
            
            # 验证缓存是否被正确写入到Redis
            result = await self._validate_cache(source_id)
            
            if result:
                logger.info(f"新闻源 '{source.name}' 缓存测试成功!")
            else:
                logger.error(f"新闻源 '{source.name}' 缓存测试失败!")
                
            return result
        except Exception as e:
            logger.error(f"测试新闻源 '{source.name}' 缓存时发生错误: {str(e)}")
            return False
    
    async def _validate_cache(self, source_id: str) -> bool:
        """验证缓存内容是否正确"""
        cache_key = f"{SOURCE_CACHE_PREFIX}{source_id}"
        
        # 检查缓存是否存在
        exists = await self.cache_manager.exists(cache_key)
        if not exists:
            logger.error(f"Redis缓存中不存在键 '{cache_key}'")
            return False
        
        # 获取缓存内容
        cached_data = await self.cache_manager.get(cache_key)
        if not cached_data:
            logger.error(f"Redis缓存键 '{cache_key}' 存在但内容为空")
            return False
        
        # 验证缓存数据格式
        if not isinstance(cached_data, list):
            logger.error(f"缓存数据不是列表类型: {type(cached_data)}")
            return False
        
        # 检查是否有内容
        if len(cached_data) == 0:
            logger.warning(f"缓存列表为空")
            # 空列表也算有效缓存
            return True
        
        # 验证条目类型
        if not all(isinstance(item, NewsItemModel) for item in cached_data):
            logger.error("缓存数据中的条目不全是NewsItemModel类型")
            return False
        
        # 获取TTL
        ttl = await self.cache_manager.get_ttl(cache_key)
        logger.info(f"缓存键 '{cache_key}' 包含 {len(cached_data)} 个条目, TTL: {ttl}秒")
        
        return True
    
    async def run_test(self, sources: List[str] = None, refresh: bool = False) -> Dict[str, bool]:
        """运行测试，检查新闻源缓存是否正常工作"""
        await self.initialize()
        
        # 如果没有指定源，测试所有源
        if not sources:
            all_sources = self.source_provider.get_all_sources()
            sources = [getattr(s, 'source_id', getattr(s, 'id', None)) for s in all_sources if hasattr(s, 'source_id') or hasattr(s, 'id')]
            logger.info(f"将测试全部 {len(sources)} 个新闻源")
        else:
            logger.info(f"将测试指定的 {len(sources)} 个新闻源: {', '.join(sources)}")
        
        results = {}
        failed_sources = []
        
        # 测试每个源
        for source_id in sources:
            success = await self.test_news_source_cache(source_id, refresh)
            results[source_id] = success
            if not success:
                failed_sources.append(source_id)
        
        # 打印摘要
        total = len(sources)
        passed = sum(1 for success in results.values() if success)
        logger.info(f"测试完成: {passed}/{total} 个新闻源通过测试")
        
        if failed_sources:
            logger.warning(f"以下新闻源测试失败: {', '.join(failed_sources)}")
        
        return results
    
    async def list_cache_keys(self, pattern: str = f"{SOURCE_CACHE_PREFIX}*") -> List[str]:
        """列出Redis中的缓存键"""
        await self.initialize()
        
        # 获取Redis客户端
        redis_client = self.cache_manager.redis
        keys = []
        
        if redis_client:
            try:
                # 使用keys命令，确保兼容性
                raw_keys = await redis_client.keys(pattern)
                keys = [key.decode('utf-8') if isinstance(key, bytes) else key for key in raw_keys]
                logger.info(f"找到 {len(keys)} 个匹配模式 '{pattern}' 的缓存键")
            except Exception as e:
                logger.error(f"获取缓存键时出错: {str(e)}")
        
        return keys
    
    async def get_cache_stats(self, pattern: str = f"{SOURCE_CACHE_PREFIX}*") -> Dict[str, Any]:
        """获取缓存的统计信息"""
        await self.initialize()
        
        keys = await self.list_cache_keys(pattern)
        stats = {
            "timestamp": datetime.now().isoformat(),
            "total_keys": len(keys),
            "keys": {},
            "total_items": 0,
            "avg_ttl": 0,
            "memory_usage": 0,
            "empty_sources": 0
        }
        
        if not keys:
            return stats
        
        redis_client = self.cache_manager.redis
        ttl_values = []
        
        # 获取每个键的详细信息
        for key in keys:
            key_stats = {
                "ttl": 0,
                "items": 0,
                "memory": 0,
                "empty": True
            }
            
            try:
                # 获取TTL
                ttl = await redis_client.ttl(key)
                key_stats["ttl"] = ttl
                if ttl > 0:
                    ttl_values.append(ttl)
                
                # 获取缓存内容
                cached_data = await self.cache_manager.get(key)
                if cached_data and isinstance(cached_data, list):
                    key_stats["items"] = len(cached_data)
                    key_stats["empty"] = len(cached_data) == 0
                    stats["total_items"] += key_stats["items"]
                    
                    if key_stats["empty"]:
                        stats["empty_sources"] += 1
                
                # 估算内存使用（如果支持）
                try:
                    # 使用MEMORY USAGE命令获取键占用的内存
                    memory = await redis_client.memory_usage(key)
                    key_stats["memory"] = memory
                    stats["memory_usage"] += memory
                except Exception:
                    # 如果命令不可用，跳过这一步
                    key_stats["memory"] = 0
                
                stats["keys"][key] = key_stats
            except Exception as e:
                logger.error(f"获取键 {key} 的信息时出错: {str(e)}")
        
        # 计算平均TTL
        if ttl_values:
            stats["avg_ttl"] = sum(ttl_values) / len(ttl_values)
        
        # 获取Redis服务器信息
        try:
            info = await redis_client.info()
            stats["redis_info"] = {
                "version": info.get("redis_version", "unknown"),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_in_days": info.get("uptime_in_days", 0)
            }
        except Exception as e:
            logger.warning(f"获取Redis信息时出错: {str(e)}")
            stats["redis_info"] = {"error": str(e)}
        
        return stats
    
    async def clear_cache(self, pattern: str = f"{SOURCE_CACHE_PREFIX}*", force: bool = False) -> int:
        """清除指定模式的缓存"""
        await self.initialize()
        
        keys = await self.list_cache_keys(pattern)
        if not keys:
            logger.info(f"没有找到匹配模式 '{pattern}' 的缓存键")
            return 0
        
        if not force:
            logger.warning(f"即将删除 {len(keys)} 个缓存键。继续操作可能会导致暂时的性能下降。")
            confirmation = input("确定要继续吗? (y/n): ").lower()
            if confirmation != 'y':
                logger.info("操作已取消")
                return 0
        
        redis_client = self.cache_manager.redis
        deleted = 0
        
        # 逐个删除键
        for key in keys:
            try:
                await redis_client.delete(key)
                deleted += 1
            except Exception as e:
                logger.error(f"删除键 '{key}' 时出错: {str(e)}")
        
        logger.info(f"已成功删除 {deleted}/{len(keys)} 个缓存键")
        return deleted
    
    async def refresh_sources(self, sources: List[str]) -> Dict[str, bool]:
        """刷新特定新闻源的缓存"""
        await self.initialize()
        
        results = {}
        for source_id in sources:
            try:
                logger.info(f"刷新新闻源 {source_id} 的缓存...")
                await self.scheduler.fetch_source(source_id, force=True)
                
                # 验证刷新后的缓存
                success = await self._validate_cache(source_id)
                results[source_id] = success
                
                if success:
                    logger.info(f"新闻源 {source_id} 缓存刷新成功")
                else:
                    logger.error(f"新闻源 {source_id} 缓存刷新失败")
            except Exception as e:
                logger.error(f"刷新新闻源 {source_id} 缓存时出错: {str(e)}")
                results[source_id] = False
        
        # 打印摘要
        total = len(sources)
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"缓存刷新完成: {success_count}/{total} 个新闻源刷新成功")
        
        return results
    
    async def export_cache_data(self, output_dir: str, sources: List[str] = None) -> int:
        """导出缓存数据到JSON文件"""
        await self.initialize()
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 确定要导出的源
        if not sources:
            keys = await self.list_cache_keys()
            sources = [key.replace(SOURCE_CACHE_PREFIX, "") for key in keys]
        
        exported = 0
        for source_id in sources:
            cache_key = f"{SOURCE_CACHE_PREFIX}{source_id}"
            
            try:
                # 获取缓存数据
                cached_data = await self.cache_manager.get(cache_key)
                if cached_data is None:
                    logger.warning(f"源 {source_id} 没有缓存数据")
                    continue
                
                # 将NewsItemModel对象转换为字典
                if isinstance(cached_data, list):
                    json_data = [
                        item.dict() if hasattr(item, "dict") else item 
                        for item in cached_data
                    ]
                else:
                    json_data = cached_data
                
                # 保存到文件
                output_file = output_path / f"{source_id}.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                
                ttl = await self.cache_manager.get_ttl(cache_key)
                logger.info(f"已导出源 {source_id} 的缓存数据 ({len(json_data) if isinstance(json_data, list) else 'N/A'} 个条目, TTL: {ttl}秒) 到 {output_file}")
                exported += 1
            except Exception as e:
                logger.error(f"导出源 {source_id} 的缓存数据时出错: {str(e)}")
        
        logger.info(f"导出完成: 已导出 {exported}/{len(sources)} 个源的缓存数据到 {output_dir}")
        return exported
    
    async def generate_html_report(self, output_file: str = "cache_report.html") -> bool:
        """生成HTML格式的缓存状态报告"""
        await self.initialize()
        
        try:
            # 获取缓存统计信息
            stats = await self.get_cache_stats()
            
            # 创建源列表，用于报告
            sources = []
            empty_source_list = []
            
            # 获取所有源
            all_sources = self.source_provider.get_all_sources()
            # 创建源ID到名称的映射
            source_map = {}
            for s in all_sources:
                source_id = getattr(s, 'source_id', getattr(s, 'id', None))
                if source_id:
                    source_map[source_id] = getattr(s, 'name', source_id)
            
            # 处理有缓存的源
            for key, key_stats in stats["keys"].items():
                source_id = key.replace(SOURCE_CACHE_PREFIX, "")
                source_name = source_map.get(source_id, source_id)
                
                # 确定状态
                status = "good"
                if key_stats["empty"]:
                    status = "danger"
                    empty_source_list.append({
                        "id": source_id,
                        "name": source_name,
                        "last_attempt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                elif key_stats["ttl"] < 60:  # TTL不足一分钟
                    status = "warning"
                
                sources.append({
                    "name": source_name,
                    "ttl": key_stats["ttl"],
                    "items": key_stats["items"],
                    "memory": self._format_size(key_stats["memory"]),
                    "status": status,
                    "last_update": self._get_relative_time(key_stats["ttl"])
                })
            
            # 处理没有缓存的源
            for source_id, source_name in source_map.items():
                cache_key = f"{SOURCE_CACHE_PREFIX}{source_id}"
                if cache_key not in stats["keys"]:
                    empty_source_list.append({
                        "id": source_id,
                        "name": source_name,
                        "last_attempt": "从未"
                    })
            
            # 准备图表数据
            if sources:
                chart_labels = [f"{s['name']} ({s['items']}条)" for s in sources if s['items'] > 0]
                chart_data = [s['items'] for s in sources if s['items'] > 0]
                
                # 限制图表条目，防止过多
                if len(chart_labels) > 8:
                    others_count = sum(chart_data[7:])
                    chart_labels = chart_labels[:7] + ["其他"]
                    chart_data = chart_data[:7] + [others_count]
            else:
                chart_labels = ["无数据"]
                chart_data = [1]
            
            # 准备警告信息
            warnings = []
            if stats["empty_sources"] > 0:
                warnings.append(f"{stats['empty_sources']} 个源的缓存为空")
            
            redis_info = stats.get("redis_info", {})
            if "error" in redis_info:
                warnings.append(f"无法获取Redis信息: {redis_info['error']}")
            
            # 计算统计数据
            source_count = len(source_map)
            avg_items_per_source = round(stats["total_items"] / max(1, len(stats["keys"])), 1)
            cache_hit_ratio = 95.5  # 模拟数据，实际应从监控中获取
            memory_used = self._format_size(stats["memory_usage"])
            redis_version = redis_info.get("version", "未知")
            latest_updated_source = sources[0]["name"] if sources else "无"
            
            # 性能指标
            avg_fetch_time = 87  # 模拟数据，实际应从监控中获取
            redis_connected = "已连接" if self.cache_manager.redis else "断开"
            redis_memory_usage = 45  # 模拟数据
            
            # 准备模板变量
            template_vars = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_keys": stats["total_keys"],
                "total_items": stats["total_items"],
                "avg_ttl": round(stats["avg_ttl"]),
                "empty_sources": len(empty_source_list),
                "warnings": warnings,
                "sources": sources,
                "empty_source_list": empty_source_list,
                "chart_labels": json.dumps(chart_labels),
                "chart_data": json.dumps(chart_data),
                "source_count": source_count,
                "avg_items_per_source": avg_items_per_source,
                "cache_hit_ratio": cache_hit_ratio,
                "memory_used": memory_used,
                "redis_version": redis_version,
                "latest_updated_source": latest_updated_source,
                "avg_fetch_time": avg_fetch_time,
                "redis_connected": redis_connected,
                "redis_memory_usage": redis_memory_usage,
                "version": "1.0.0"
            }
            
            # 加载模板并渲染
            template_dir = Path(__file__).parent / "templates"
            env = Environment(loader=FileSystemLoader(template_dir))
            template = env.get_template("cache_report_template.html")
            html_content = template.render(**template_vars)
            
            # 写入输出文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"已生成HTML报告: {output_file}")
            return True
        except Exception as e:
            logger.error(f"生成HTML报告时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _format_size(self, size_bytes: int) -> str:
        """将字节数格式化为人类可读的形式"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"
    
    def _get_relative_time(self, ttl: int) -> str:
        """根据TTL估算最后更新时间"""
        # 假设TTL就是从最后更新时刻开始计算的
        sources = self.source_provider.get_all_sources()
        source = sources[0] if sources else None  # 获取任意一个源
        if not source:
            return "未知"
            
        cache_ttl = getattr(source, "cache_ttl", 3600)  # 默认1小时
        elapsed_seconds = max(0, cache_ttl - ttl)
        
        if elapsed_seconds < 60:
            return "刚刚"
        elif elapsed_seconds < 3600:
            return f"{int(elapsed_seconds / 60)}分钟前"
        elif elapsed_seconds < 86400:
            return f"{int(elapsed_seconds / 3600)}小时前"
        else:
            return f"{int(elapsed_seconds / 86400)}天前"


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Redis缓存监控工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # test命令
    test_parser = subparsers.add_parser("test", help="测试新闻源缓存集成")
    test_parser.add_argument("--sources", help="要测试的新闻源ID，逗号分隔")
    test_parser.add_argument("--refresh", action="store_true", help="强制刷新缓存后测试")
    
    # stats命令
    stats_parser = subparsers.add_parser("stats", help="获取缓存统计信息")
    stats_parser.add_argument("--pattern", default=f"{SOURCE_CACHE_PREFIX}*", help="键匹配模式")
    stats_parser.add_argument("--json", action="store_true", help="以JSON格式输出")
    
    # clear命令
    clear_parser = subparsers.add_parser("clear", help="清除缓存")
    clear_parser.add_argument("--pattern", default=f"{SOURCE_CACHE_PREFIX}*", help="键匹配模式")
    clear_parser.add_argument("--force", action="store_true", help="强制清除，不需要确认")
    
    # refresh命令
    refresh_parser = subparsers.add_parser("refresh", help="刷新特定新闻源的缓存")
    refresh_parser.add_argument("--sources", required=True, help="要刷新的新闻源ID，逗号分隔")
    
    # list命令
    list_parser = subparsers.add_parser("list", help="列出缓存键")
    list_parser.add_argument("--pattern", default=f"{SOURCE_CACHE_PREFIX}*", help="键匹配模式")
    
    # export命令
    export_parser = subparsers.add_parser("export", help="导出缓存数据")
    export_parser.add_argument("--output", required=True, help="输出目录")
    export_parser.add_argument("--sources", help="要导出的新闻源ID，逗号分隔")
    
    # report命令
    report_parser = subparsers.add_parser("report", help="生成HTML报告")
    report_parser.add_argument("--output", default="cache_report.html", help="输出文件名")
    
    # 通用选项
    parser.add_argument("--redis-url", help="Redis URL")
    
    # 解析参数
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    
    # 创建监控器
    monitor = RedisCacheMonitor(args.redis_url)
    
    try:
        # 执行命令
        if args.command == "test":
            sources = args.sources.split(",") if args.sources else None
            results = await monitor.run_test(sources, args.refresh)
            success = all(results.values())
            sys.exit(0 if success else 1)
        
        elif args.command == "stats":
            stats = await monitor.get_cache_stats(args.pattern)
            if args.json:
                print(json.dumps(stats, indent=2, ensure_ascii=False))
            else:
                print(f"缓存状态统计 (时间: {stats['timestamp']})")
                print(f"总缓存键数: {stats['total_keys']}")
                print(f"总条目数: {stats['total_items']}")
                print(f"平均TTL: {stats['avg_ttl']:.1f}秒")
                print(f"内存使用: {monitor._format_size(stats['memory_usage'])}")
                print(f"空缓存源数: {stats['empty_sources']}")
                
                if stats["keys"]:
                    print("\n各源缓存状态:")
                    for key, key_stats in stats["keys"].items():
                        source_id = key.replace(SOURCE_CACHE_PREFIX, "")
                        print(f"  {source_id}: {key_stats['items']}条目, TTL: {key_stats['ttl']}秒, 内存: {monitor._format_size(key_stats['memory'])}")
        
        elif args.command == "clear":
            deleted = await monitor.clear_cache(args.pattern, args.force)
            print(f"已删除 {deleted} 个缓存键")
        
        elif args.command == "refresh":
            sources = args.sources.split(",")
            results = await monitor.refresh_sources(sources)
            success = all(results.values())
            sys.exit(0 if success else 1)
        
        elif args.command == "list":
            keys = await monitor.list_cache_keys(args.pattern)
            for key in keys:
                print(key)
        
        elif args.command == "export":
            sources = args.sources.split(",") if args.sources else None
            exported = await monitor.export_cache_data(args.output, sources)
            print(f"已导出 {exported} 个源的缓存数据")
        
        elif args.command == "report":
            success = await monitor.generate_html_report(args.output)
            if success:
                print(f"已生成HTML报告: {args.output}")
                print(f"可以使用浏览器打开查看")
            else:
                print("生成HTML报告失败")
                sys.exit(1)
    
    finally:
        # 清理资源
        await monitor.cleanup()


if __name__ == "__main__":
    asyncio.run(main()) 