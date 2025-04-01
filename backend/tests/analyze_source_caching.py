#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析各个主要新闻源类型的缓存机制实现
"""

import os
import sys
import inspect
import asyncio
import logging
import traceback
from typing import List, Dict, Any, Tuple, Set, Optional
import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cache_analysis")

# 设置调试模式
os.environ["DEBUG"] = "1"

class CacheAnalyzer:
    """新闻源缓存机制分析器"""
    
    def __init__(self):
        self.source_classes = {}  # 类名 -> 类对象的映射
        self.source_instances = {}  # 源ID -> 实例对象的映射
        self.cache_implementations = {}  # 类名 -> 缓存实现类型的映射
        self.custom_cache_fields = {}  # 类名 -> 自定义缓存字段的映射
        
        # 要检查的缓存相关方法
        self.cache_methods = [
            "is_cache_valid",
            "update_cache",
            "clear_cache",
            "get_news",
            "fetch"
        ]
        
        # 要检查的缓存相关字段
        self.cache_fields = [
            "_cached_news_items",
            "_last_cache_update",
            "_news_cache",
            "_cache_ttl",
            "cache_ttl"
        ]
    
    async def load_source_classes(self):
        """动态加载所有新闻源类"""
        from worker.sources.provider import DefaultNewsSourceProvider
        from worker.sources.base import NewsSource
        
        # 记录NewsSource基类的方法实现
        self.base_class = NewsSource
        self.base_class_methods = {}
        for method_name in self.cache_methods:
            if hasattr(NewsSource, method_name):
                method = getattr(NewsSource, method_name)
                self.base_class_methods[method_name] = inspect.getsource(method)
        
        # 获取所有源适配器
        provider = DefaultNewsSourceProvider()
        source_ids = [source.source_id for source in provider.get_all_sources()]
        logger.info(f"找到 {len(source_ids)} 个新闻源ID")
        
        # 分析每个源的类
        for source_id in source_ids:
            try:
                # 获取源实例
                source = provider.get_source(source_id)
                if not source:
                    logger.warning(f"无法获取源 {source_id} 的实例")
                    continue
                
                # 记录类和实例
                class_name = source.__class__.__name__
                self.source_classes[class_name] = source.__class__
                self.source_instances[source_id] = source
                
                logger.info(f"已加载源 {source_id} (类型: {class_name})")
            except Exception as e:
                logger.error(f"加载源 {source_id} 时出错: {str(e)}")
    
    def analyze_inheritance(self):
        """分析类继承关系"""
        logger.info("=== 分析新闻源类的继承关系 ===")
        
        class_hierarchy = {}
        for class_name, cls in self.source_classes.items():
            # 获取类的继承链
            hierarchy = []
            for base in cls.__mro__[1:]:  # 跳过自身
                if base.__name__ != 'object':
                    hierarchy.append(base.__name__)
            
            class_hierarchy[class_name] = hierarchy
            logger.info(f"{class_name} 继承自: {' -> '.join(hierarchy)}")
        
        return class_hierarchy
    
    def analyze_method_overrides(self):
        """分析方法重写情况"""
        logger.info("=== 分析缓存相关方法的重写情况 ===")
        
        method_overrides = {}
        for class_name, cls in self.source_classes.items():
            overrides = {}
            for method_name in self.cache_methods:
                if hasattr(cls, method_name):
                    method = getattr(cls, method_name)
                    
                    # 检查方法是否是从基类继承的
                    for base in cls.__mro__[1:]:
                        if hasattr(base, method_name) and getattr(base, method_name) == method:
                            overrides[method_name] = f"继承自 {base.__name__}"
                            break
                    else:
                        # 方法被重写
                        overrides[method_name] = "重写"
                else:
                    overrides[method_name] = "未实现"
            
            method_overrides[class_name] = overrides
            logger.info(f"{class_name} 的方法重写情况:")
            for method, status in overrides.items():
                logger.info(f"  - {method}: {status}")
        
        return method_overrides
    
    def analyze_cache_fields(self):
        """分析缓存相关字段"""
        logger.info("=== 分析缓存相关字段 ===")
        
        field_usage = {}
        for source_id, source in self.source_instances.items():
            class_name = source.__class__.__name__
            fields = {}
            
            # 检查是否有缓存相关字段
            for field in self.cache_fields:
                if hasattr(source, field):
                    fields[field] = f"存在 ({type(getattr(source, field)).__name__})"
                else:
                    fields[field] = "不存在"
            
            field_usage[class_name] = fields
            logger.info(f"{class_name} ({source_id}) 的缓存字段:")
            for field, status in fields.items():
                logger.info(f"  - {field}: {status}")
        
        return field_usage
    
    def analyze_cache_implementation(self):
        """分析缓存实现类型"""
        logger.info("=== 分析缓存实现类型 ===")
        
        cache_types = {}
        custom_cache_fields = {}
        
        for class_name, cls in self.source_classes.items():
            # 检查是否有自定义的is_cache_valid方法
            has_custom_cache_valid = False
            if hasattr(cls, "is_cache_valid"):
                method = getattr(cls, "is_cache_valid")
                for base in cls.__mro__[1:]:
                    if hasattr(base, "is_cache_valid") and getattr(base, "is_cache_valid") == method:
                        has_custom_cache_valid = False
                        break
                else:
                    has_custom_cache_valid = True
            
            # 检查是否有自定义的update_cache方法
            has_custom_update_cache = False
            if hasattr(cls, "update_cache"):
                method = getattr(cls, "update_cache")
                for base in cls.__mro__[1:]:
                    if hasattr(base, "update_cache") and getattr(base, "update_cache") == method:
                        has_custom_update_cache = False
                        break
                else:
                    has_custom_update_cache = True
            
            # 检查是否有自定义的fetch方法
            has_custom_fetch = False
            if hasattr(cls, "fetch"):
                method = getattr(cls, "fetch")
                for base in cls.__mro__[1:]:
                    if hasattr(base, "fetch") and getattr(base, "fetch") == method:
                        has_custom_fetch = False
                        break
                else:
                    has_custom_fetch = True
            
            # 确定缓存实现类型
            if has_custom_cache_valid and has_custom_update_cache:
                impl_type = "自定义缓存实现"
            elif has_custom_fetch and not has_custom_cache_valid:
                impl_type = "自定义fetch但使用基类缓存"
            else:
                impl_type = "使用基类缓存实现"
            
            cache_types[class_name] = impl_type
            
            # 查找自定义缓存字段
            custom_fields = set()
            for source_id, source in self.source_instances.items():
                if source.__class__.__name__ == class_name:
                    for attr in dir(source):
                        if attr.startswith('_') and 'cache' in attr.lower() and attr not in self.cache_fields:
                            custom_fields.add(attr)
            
            if custom_fields:
                custom_cache_fields[class_name] = list(custom_fields)
                logger.info(f"{class_name} 使用 {impl_type}，自定义缓存字段: {', '.join(custom_fields)}")
            else:
                logger.info(f"{class_name} 使用 {impl_type}")
        
        self.cache_implementations = cache_types
        self.custom_cache_fields = custom_cache_fields
        return cache_types
    
    def analyze_method_content(self):
        """分析方法内容中的缓存相关代码"""
        logger.info("=== 分析方法内容中的缓存相关代码 ===")
        
        cache_patterns = {
            "检查缓存": ["cache", "_news_cache", "_cached_news_items", "is_cache_valid"],
            "更新缓存": ["update_cache", "self._news_cache =", "self._cached_news_items =", "self._last_cache_update ="],
            "缓存锁": ["_cache_lock", "asyncio.Lock()", "async with self._cache_lock"],
            "缓存时间": ["cache_ttl", "self._cache_ttl", "time.time()", "current_time - self._last_cache_update"]
        }
        
        method_content_analysis = {}
        
        for class_name, cls in self.source_classes.items():
            class_analysis = {}
            
            for method_name in self.cache_methods:
                if not hasattr(cls, method_name):
                    continue
                
                method = getattr(cls, method_name)
                
                # 跳过直接继承的方法
                is_inherited = False
                for base in cls.__mro__[1:]:
                    if hasattr(base, method_name) and getattr(base, method_name) == method:
                        is_inherited = True
                        break
                
                if is_inherited:
                    continue
                
                # 获取方法源代码
                try:
                    source_code = inspect.getsource(method)
                    
                    # 分析源代码中的缓存模式
                    patterns_found = {}
                    for pattern_name, keywords in cache_patterns.items():
                        found = False
                        for keyword in keywords:
                            if keyword in source_code:
                                found = True
                                break
                        patterns_found[pattern_name] = found
                    
                    class_analysis[method_name] = patterns_found
                    
                    # 输出分析结果
                    logger.info(f"{class_name}.{method_name} 包含以下缓存模式:")
                    for pattern, found in patterns_found.items():
                        logger.info(f"  - {pattern}: {'是' if found else '否'}")
                        
                except (OSError, TypeError):
                    logger.warning(f"无法获取 {class_name}.{method_name} 的源代码")
            
            method_content_analysis[class_name] = class_analysis
        
        return method_content_analysis
    
    async def analyze_cache_behavior(self):
        """分析缓存行为"""
        logger.info("=== 分析缓存行为 ===")
        
        behavior_analysis = {}
        
        # 选择一些代表性的源进行行为测试
        test_sources = []
        source_types = set()
        
        for source_id, source in self.source_instances.items():
            class_name = source.__class__.__name__
            if class_name not in source_types and len(test_sources) < 10:
                source_types.add(class_name)
                test_sources.append((source_id, source))
        
        logger.info(f"选择了 {len(test_sources)} 个代表性源进行行为测试")
        
        for source_id, source in test_sources:
            class_name = source.__class__.__name__
            logger.info(f"测试源 {source_id} ({class_name}) 的缓存行为")
            
            analysis = {
                "首次获取": None,
                "再次获取": None,
                "强制更新": None,
                "使用缓存": None
            }
            
            try:
                # 1. 首次获取（不强制更新）
                logger.info("1. 首次获取（不强制更新）")
                start_time = datetime.datetime.now()
                news1 = await source.get_news(force_update=False)
                end_time = datetime.datetime.now()
                elapsed1 = (end_time - start_time).total_seconds()
                
                analysis["首次获取"] = {
                    "项目数": len(news1),
                    "耗时": elapsed1,
                    "使用缓存": "未知"
                }
                logger.info(f"  获取到 {len(news1)} 条新闻，耗时 {elapsed1:.2f} 秒")
                
                # 2. 再次获取（不强制更新）
                logger.info("2. 再次获取（不强制更新）")
                start_time = datetime.datetime.now()
                news2 = await source.get_news(force_update=False)
                end_time = datetime.datetime.now()
                elapsed2 = (end_time - start_time).total_seconds()
                
                analysis["再次获取"] = {
                    "项目数": len(news2),
                    "耗时": elapsed2,
                    "使用缓存": elapsed2 < elapsed1 * 0.5  # 如果时间明显减少，可能使用了缓存
                }
                logger.info(f"  获取到 {len(news2)} 条新闻，耗时 {elapsed2:.2f} 秒")
                logger.info(f"  {'似乎使用了缓存' if analysis['再次获取']['使用缓存'] else '似乎未使用缓存'}")
                
                # 3. 强制更新
                logger.info("3. 强制更新")
                start_time = datetime.datetime.now()
                news3 = await source.get_news(force_update=True)
                end_time = datetime.datetime.now()
                elapsed3 = (end_time - start_time).total_seconds()
                
                analysis["强制更新"] = {
                    "项目数": len(news3),
                    "耗时": elapsed3,
                    "使用缓存": False  # 强制更新不应使用缓存
                }
                logger.info(f"  获取到 {len(news3)} 条新闻，耗时 {elapsed3:.2f} 秒")
                
                # 4. 再次获取（不强制更新，应该使用缓存）
                logger.info("4. 再次获取（不强制更新，应该使用缓存）")
                start_time = datetime.datetime.now()
                news4 = await source.get_news(force_update=False)
                end_time = datetime.datetime.now()
                elapsed4 = (end_time - start_time).total_seconds()
                
                analysis["使用缓存"] = {
                    "项目数": len(news4),
                    "耗时": elapsed4,
                    "使用缓存": elapsed4 < elapsed3 * 0.5  # 如果时间明显减少，可能使用了缓存
                }
                logger.info(f"  获取到 {len(news4)} 条新闻，耗时 {elapsed4:.2f} 秒")
                logger.info(f"  {'似乎使用了缓存' if analysis['使用缓存']['使用缓存'] else '似乎未使用缓存'}")
                
                # 检查新闻项是否相同（简单比较）
                if len(news3) > 0 and len(news4) > 0:
                    same_ids = sum(1 for item1 in news3 if any(item2.id == item1.id for item2 in news4))
                    logger.info(f"  新闻ID匹配率: {same_ids / len(news3) * 100:.1f}%")
                
                behavior_analysis[class_name] = analysis
            except Exception as e:
                logger.error(f"测试源 {source_id} 时出错: {str(e)}")
                logger.error(traceback.format_exc())
        
        return behavior_analysis
    
    def generate_summary(self):
        """生成摘要报告"""
        logger.info("=== 生成摘要报告 ===")
        
        # 按缓存实现类型分组
        groups = {}
        for class_name, impl_type in self.cache_implementations.items():
            if impl_type not in groups:
                groups[impl_type] = []
            groups[impl_type].append(class_name)
        
        # 输出分组结果
        logger.info("新闻源缓存实现分类:")
        for impl_type, class_names in groups.items():
            logger.info(f"【{impl_type}】({len(class_names)}个)")
            for class_name in class_names:
                # 获取这个类的一个实例的源ID
                source_id = next((sid for sid, src in self.source_instances.items() 
                                 if src.__class__.__name__ == class_name), "unknown")
                logger.info(f"  - {class_name} (示例ID: {source_id})")
        
        # 生成建议
        logger.info("\n=== 优化建议 ===")
        
        custom_impl_classes = groups.get("自定义缓存实现", [])
        if custom_impl_classes:
            logger.info("1. 以下类使用自定义缓存实现，可能需要更新以兼容基类缓存:")
            for class_name in custom_impl_classes:
                custom_fields = self.custom_cache_fields.get(class_name, [])
                fields_str = f"(使用字段: {', '.join(custom_fields)})" if custom_fields else ""
                logger.info(f"  - {class_name} {fields_str}")
        
        # 报告继承情况
        logger.info("\n2. 缓存方法继承情况:")
        method_stats = {method: {"自定义": 0, "继承": 0, "未实现": 0} for method in self.cache_methods}
        
        for class_name, cls in self.source_classes.items():
            for method_name in self.cache_methods:
                if not hasattr(cls, method_name):
                    method_stats[method_name]["未实现"] += 1
                    continue
                
                method = getattr(cls, method_name)
                
                # 检查是否是继承的方法
                is_inherited = False
                for base in cls.__mro__[1:]:
                    if hasattr(base, method_name) and getattr(base, method_name) == method:
                        is_inherited = True
                        break
                
                if is_inherited:
                    method_stats[method_name]["继承"] += 1
                else:
                    method_stats[method_name]["自定义"] += 1
        
        for method_name, stats in method_stats.items():
            logger.info(f"  - {method_name}: {stats['自定义']}个自定义, {stats['继承']}个继承, {stats['未实现']}个未实现")
        
        # 总结缓存字段使用情况
        logger.info("\n3. 缓存字段使用情况:")
        field_stats = {field: 0 for field in self.cache_fields}
        
        for class_name, fields in self.custom_cache_fields.items():
            for field in fields:
                if field not in field_stats:
                    field_stats[field] = 0
                field_stats[field] += 1
        
        for field, count in field_stats.items():
            logger.info(f"  - {field}: {count}个类使用")

async def main():
    """主函数"""
    logger.info("开始分析新闻源缓存机制")
    
    analyzer = CacheAnalyzer()
    await analyzer.load_source_classes()
    
    # 运行分析
    hierarchy = analyzer.analyze_inheritance()
    method_overrides = analyzer.analyze_method_overrides()
    field_usage = analyzer.analyze_cache_fields()
    cache_impls = analyzer.analyze_cache_implementation()
    method_content = analyzer.analyze_method_content()
    behavior = await analyzer.analyze_cache_behavior()
    
    # 生成摘要
    analyzer.generate_summary()
    
    logger.info("缓存机制分析完成")

if __name__ == "__main__":
    asyncio.run(main()) 