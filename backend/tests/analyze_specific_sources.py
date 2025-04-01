#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
针对特定新闻源的缓存分析脚本
重点关注IfengBaseSource类和36kr适配器的缓存机制
"""

import os
import sys
import inspect
import asyncio
import logging
import time
import traceback
from typing import List, Dict, Any, Optional
import datetime
import json

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("specific_source_analysis.log")
    ]
)
logger = logging.getLogger("specific_analysis")

# 设置调试模式
os.environ["DEBUG"] = "1"

# 要分析的特定源ID
TARGET_SOURCES = [
    "ifeng-tech",
    "ifeng-studio",
    "36kr",
    "yicai-news",
    "bilibili",
    "thepaper",
    "weibo",
    "kaopu"
]

class SourceAnalyzer:
    """特定新闻源分析器"""
    
    def __init__(self, source_ids):
        self.source_ids = source_ids
        self.sources = {}  # 源ID -> 源实例
        self.source_classes = {}  # 源ID -> 源类
        self.test_results = {}  # 源ID -> 测试结果
    
    async def load_sources(self):
        """加载指定的新闻源"""
        from worker.sources.provider import DefaultNewsSourceProvider
        
        provider = DefaultNewsSourceProvider()
        for source_id in self.source_ids:
            try:
                source = provider.get_source(source_id)
                if source:
                    self.sources[source_id] = source
                    self.source_classes[source_id] = source.__class__
                    logger.info(f"已加载源: {source_id} (类型: {source.__class__.__name__})")
                else:
                    logger.warning(f"无法加载源: {source_id}")
            except Exception as e:
                logger.error(f"加载源 {source_id} 时出错: {str(e)}")
                logger.error(traceback.format_exc())
    
    def analyze_cache_methods(self):
        """分析缓存相关方法"""
        logger.info("=== 分析缓存相关方法 ===")
        
        cache_methods = ["is_cache_valid", "update_cache", "clear_cache", "get_news", "fetch"]
        method_analysis = {}
        
        for source_id, source in self.sources.items():
            class_name = source.__class__.__name__
            logger.info(f"分析源 {source_id} ({class_name}) 的缓存方法")
            
            method_info = {}
            
            for method_name in cache_methods:
                if not hasattr(source.__class__, method_name):
                    method_info[method_name] = {"存在": False}
                    continue
                
                method = getattr(source.__class__, method_name)
                method_info[method_name] = {
                    "存在": True,
                    "是否重写": True,  # 默认假设是重写的
                }
                
                # 检查是否是继承的方法
                for base in source.__class__.__mro__[1:]:
                    if hasattr(base, method_name) and getattr(base, method_name) == method:
                        method_info[method_name]["是否重写"] = False
                        method_info[method_name]["继承自"] = base.__name__
                        break
                
                # 获取方法源代码（如果是重写的）
                if method_info[method_name]["是否重写"]:
                    try:
                        source_code = inspect.getsource(method)
                        # 检查源代码中的关键字
                        cache_keywords = [
                            "cache", "_news_cache", "_cached_news_items", 
                            "self._last_cache_update", "time.time()", "cache_ttl"
                        ]
                        
                        keywords_found = []
                        for keyword in cache_keywords:
                            if keyword in source_code:
                                keywords_found.append(keyword)
                        
                        method_info[method_name]["关键字"] = keywords_found
                        method_info[method_name]["源代码"] = source_code
                    except Exception as e:
                        logger.warning(f"获取 {method_name} 源代码失败: {str(e)}")
            
            method_analysis[source_id] = method_info
            
            # 打印分析结果
            for method_name, info in method_info.items():
                if not info["存在"]:
                    logger.info(f"  {method_name}: 不存在")
                    continue
                
                if info["是否重写"]:
                    keywords = ", ".join(info.get("关键字", []))
                    logger.info(f"  {method_name}: 重写 (关键字: {keywords})")
                else:
                    logger.info(f"  {method_name}: 继承自 {info.get('继承自', '未知')}")
        
        return method_analysis
    
    def analyze_cache_fields(self):
        """分析缓存相关字段"""
        logger.info("=== 分析缓存相关字段 ===")
        
        cache_fields = [
            "_cached_news_items",
            "_last_cache_update",
            "_news_cache",
            "_cache_ttl",
            "cache_ttl",
            "_cache_lock"
        ]
        
        field_analysis = {}
        
        for source_id, source in self.sources.items():
            class_name = source.__class__.__name__
            logger.info(f"分析源 {source_id} ({class_name}) 的缓存字段")
            
            field_info = {}
            
            for field in cache_fields:
                if hasattr(source, field):
                    value = getattr(source, field)
                    field_info[field] = {
                        "存在": True,
                        "类型": type(value).__name__,
                        "值": str(value) if not isinstance(value, list) else f"List[{len(value)}]"
                    }
                else:
                    field_info[field] = {"存在": False}
            
            # 检查__init__方法中是否初始化了缓存字段
            if hasattr(source.__class__, "__init__"):
                try:
                    init_code = inspect.getsource(source.__class__.__init__)
                    
                    for field in cache_fields:
                        if field in init_code:
                            if field in field_info:
                                field_info[field]["在初始化中"] = True
                            else:
                                field_info[field] = {
                                    "存在": False,
                                    "在初始化中": True
                                }
                except Exception as e:
                    logger.warning(f"获取 {class_name}.__init__ 源代码失败: {str(e)}")
            
            field_analysis[source_id] = field_info
            
            # 打印分析结果
            for field, info in field_info.items():
                if info["存在"]:
                    logger.info(f"  {field}: {info['类型']} = {info['值']}")
                else:
                    in_init = "在__init__中初始化" if info.get("在初始化中") else "完全不存在"
                    logger.info(f"  {field}: {in_init}")
        
        return field_analysis
    
    async def test_caching_behavior(self):
        """测试缓存行为"""
        logger.info("=== 测试缓存行为 ===")
        
        for source_id, source in self.sources.items():
            class_name = source.__class__.__name__
            logger.info(f"测试源 {source_id} ({class_name}) 的缓存行为")
            
            cache_test = {}
            
            try:
                # 运行不同的测试场景
                
                # 场景1: 先调用get_news，然后调用fetch，检查是否重用缓存
                logger.info("场景1: 测试get_news和fetch的缓存交互")
                
                # 第一步: 调用get_news (这应该会更新缓存)
                start = time.time()
                news1 = await source.get_news(force_update=True)
                time1 = time.time() - start
                
                cache_test["get_news"] = {
                    "耗时": time1,
                    "项目数": len(news1) if news1 else 0
                }
                logger.info(f"  get_news: 获取到 {len(news1) if news1 else 0} 条新闻，耗时 {time1:.2f} 秒")
                
                # 第二步: 调用fetch (如果共享缓存，应该很快)
                start = time.time()
                news2 = await source.fetch()
                time2 = time.time() - start
                
                cache_test["fetch"] = {
                    "耗时": time2,
                    "项目数": len(news2) if news2 else 0,
                    "使用缓存": time2 < time1 * 0.5  # 如果明显更快，可能用了缓存
                }
                logger.info(f"  fetch: 获取到 {len(news2) if news2 else 0} 条新闻，耗时 {time2:.2f} 秒")
                logger.info(f"  fetch {'似乎使用了缓存' if cache_test['fetch']['使用缓存'] else '似乎没有使用缓存'}")
                
                # 场景2: 测试get_news的缓存效果
                logger.info("场景2: 测试get_news的缓存效果")
                
                # 第一次调用get_news (强制更新)
                start = time.time()
                news3 = await source.get_news(force_update=True)
                time3 = time.time() - start
                
                cache_test["get_news_force"] = {
                    "耗时": time3,
                    "项目数": len(news3) if news3 else 0
                }
                logger.info(f"  get_news(force=True): 获取到 {len(news3) if news3 else 0} 条新闻，耗时 {time3:.2f} 秒")
                
                # 第二次调用get_news (不强制更新，应该使用缓存)
                start = time.time()
                news4 = await source.get_news(force_update=False)
                time4 = time.time() - start
                
                cache_test["get_news_cache"] = {
                    "耗时": time4,
                    "项目数": len(news4) if news4 else 0,
                    "使用缓存": time4 < time3 * 0.5  # 如果明显更快，可能用了缓存
                }
                logger.info(f"  get_news(force=False): 获取到 {len(news4) if news4 else 0} 条新闻，耗时 {time4:.2f} 秒")
                logger.info(f"  get_news {'似乎使用了缓存' if cache_test['get_news_cache']['使用缓存'] else '似乎没有使用缓存'}")
                
                # 检查新闻项是否相同
                if news3 and news4:
                    same_ids = sum(1 for item1 in news3 if any(item2.id == item1.id for item2 in news4))
                    match_rate = same_ids / max(len(news3), 1) * 100
                    cache_test["id_match_rate"] = match_rate
                    logger.info(f"  新闻ID匹配率: {match_rate:.1f}%")
                
                # 场景3: 测试缓存清理
                logger.info("场景3: 测试缓存清理")
                
                # 先确保有缓存数据
                await source.get_news(force_update=True)
                
                # 清理缓存
                if hasattr(source, "clear_cache"):
                    start = time.time()
                    await source.clear_cache()
                    time5 = time.time() - start
                    
                    # 清理后再次获取（应该重新获取而不使用缓存）
                    start = time.time()
                    news5 = await source.get_news(force_update=False)
                    time6 = time.time() - start
                    
                    cache_test["clear_cache"] = {
                        "支持": True,
                        "清理耗时": time5,
                        "清理后获取耗时": time6,
                        "清理后获取项目数": len(news5) if news5 else 0,
                        "清理有效": time6 > time4 * 0.8  # 如果明显变慢，说明缓存清理有效
                    }
                    logger.info(f"  clear_cache: 清理耗时 {time5:.2f} 秒")
                    logger.info(f"  清理后 get_news: 获取到 {len(news5) if news5 else 0} 条新闻，耗时 {time6:.2f} 秒")
                    logger.info(f"  缓存清理 {'有效' if cache_test['clear_cache']['清理有效'] else '似乎无效'}")
                else:
                    cache_test["clear_cache"] = {"支持": False}
                    logger.info("  不支持clear_cache方法")
                
                self.test_results[source_id] = cache_test
            except Exception as e:
                logger.error(f"测试源 {source_id} 时出错: {str(e)}")
                logger.error(traceback.format_exc())
                self.test_results[source_id] = {"错误": str(e)}
        
        return self.test_results
    
    def analyze_shared_cache_usage(self):
        """分析共享缓存的使用情况"""
        logger.info("=== 分析共享缓存使用情况 ===")
        
        from worker.sources.base import NewsSource
        
        # 检查NewsSource基类的缓存实现
        logger.info("NewsSource基类的缓存实现:")
        
        base_cache_fields = []
        base_cache_methods = []
        
        for attr in dir(NewsSource):
            if attr.startswith("_") and "cache" in attr.lower():
                base_cache_fields.append(attr)
            elif not attr.startswith("_") and any(x in attr.lower() for x in ["cache", "get_news"]):
                if callable(getattr(NewsSource, attr)):
                    base_cache_methods.append(attr)
        
        logger.info(f"  缓存相关字段: {', '.join(base_cache_fields)}")
        logger.info(f"  缓存相关方法: {', '.join(base_cache_methods)}")
        
        # 检查源是否使用了基类的缓存字段
        shared_cache_analysis = {}
        
        for source_id, source in self.sources.items():
            class_name = source.__class__.__name__
            logger.info(f"分析源 {source_id} ({class_name}) 的共享缓存使用情况")
            
            analysis = {
                "使用基类缓存字段": False,
                "使用自定义缓存字段": False,
                "自定义字段": [],
                "基类字段": []
            }
            
            # 检查基类缓存字段
            for field in base_cache_fields:
                if hasattr(source, field):
                    analysis["使用基类缓存字段"] = True
                    analysis["基类字段"].append(field)
            
            # 检查自定义缓存字段
            for attr in dir(source):
                if attr.startswith("_") and "cache" in attr.lower() and attr not in base_cache_fields:
                    analysis["使用自定义缓存字段"] = True
                    analysis["自定义字段"].append(attr)
            
            # 判断缓存使用类型
            if analysis["使用基类缓存字段"] and not analysis["使用自定义缓存字段"]:
                analysis["缓存类型"] = "仅使用基类缓存"
            elif not analysis["使用基类缓存字段"] and analysis["使用自定义缓存字段"]:
                analysis["缓存类型"] = "仅使用自定义缓存"
            elif analysis["使用基类缓存字段"] and analysis["使用自定义缓存字段"]:
                analysis["缓存类型"] = "混合使用缓存"
            else:
                analysis["缓存类型"] = "未检测到缓存字段"
            
            shared_cache_analysis[source_id] = analysis
            
            # 打印分析结果
            logger.info(f"  缓存类型: {analysis['缓存类型']}")
            if analysis["基类字段"]:
                logger.info(f"  使用的基类缓存字段: {', '.join(analysis['基类字段'])}")
            if analysis["自定义字段"]:
                logger.info(f"  使用的自定义缓存字段: {', '.join(analysis['自定义字段'])}")
        
        return shared_cache_analysis
    
    def check_for_issues(self, method_analysis, field_analysis, cache_test_results, shared_cache_analysis):
        """检查潜在问题并生成建议"""
        logger.info("=== 潜在问题检查 ===")
        
        issues = {}
        
        for source_id in self.sources:
            source_issues = []
            class_name = self.sources[source_id].__class__.__name__
            
            # 问题1: 混合使用缓存 (可能导致不一致)
            if shared_cache_analysis.get(source_id, {}).get("缓存类型") == "混合使用缓存":
                source_issues.append({
                    "级别": "警告",
                    "问题": "混合使用基类和自定义缓存字段",
                    "影响": "可能导致缓存不一致，部分数据未正确缓存",
                    "建议": "统一使用基类缓存字段，移除自定义缓存字段"
                })
            
            # 问题2: 重写了fetch但未重写缓存方法
            if method_analysis.get(source_id, {}).get("fetch", {}).get("是否重写", False) and \
               not method_analysis.get(source_id, {}).get("is_cache_valid", {}).get("是否重写", False):
                source_issues.append({
                    "级别": "信息",
                    "问题": "重写了fetch方法但使用基类缓存验证",
                    "影响": "可能导致特定源的缓存逻辑不一致",
                    "建议": "确保fetch方法正确使用基类缓存机制"
                })
            
            # 问题3: 缓存测试中发现的问题
            test_results = cache_test_results.get(source_id, {})
            
            # 3.1 get_news未使用缓存
            if test_results.get("get_news_cache", {}).get("使用缓存") is False:
                source_issues.append({
                    "级别": "错误",
                    "问题": "get_news方法不使用缓存",
                    "影响": "每次调用都会重新获取数据，性能低下",
                    "建议": "检查get_news方法实现，确保使用缓存"
                })
            
            # 3.2 clear_cache无效
            if test_results.get("clear_cache", {}).get("支持") is True and \
               test_results.get("clear_cache", {}).get("清理有效") is False:
                source_issues.append({
                    "级别": "警告",
                    "问题": "clear_cache方法似乎无效",
                    "影响": "可能导致无法刷新过期缓存",
                    "建议": "检查clear_cache方法实现，确保清理所有缓存字段"
                })
            
            # 3.3 fetch和get_news缓存不共享
            get_news_time = test_results.get("get_news", {}).get("耗时", 0)
            fetch_time = test_results.get("fetch", {}).get("耗时", 0)
            
            if get_news_time > 0 and fetch_time > get_news_time * 0.5:
                source_issues.append({
                    "级别": "警告",
                    "问题": "fetch和get_news缓存似乎不共享",
                    "影响": "可能导致冗余数据获取，性能低下",
                    "建议": "确保fetch和get_news使用相同的缓存存储"
                })
            
            issues[source_id] = source_issues
            
            # 打印分析结果
            logger.info(f"源 {source_id} ({class_name}) 的潜在问题:")
            if not source_issues:
                logger.info("  未发现明显问题")
            else:
                for issue in source_issues:
                    logger.info(f"  [{issue['级别']}] {issue['问题']}")
                    logger.info(f"    影响: {issue['影响']}")
                    logger.info(f"    建议: {issue['建议']}")
        
        return issues
    
    def generate_recommendations(self, issues):
        """生成优化建议"""
        logger.info("=== 优化建议 ===")
        
        # 按问题类型分组源
        problem_groups = {
            "混合缓存": [],
            "缓存不共享": [],
            "缓存不生效": [],
            "其他问题": []
        }
        
        for source_id, source_issues in issues.items():
            class_name = self.sources[source_id].__class__.__name__
            source_info = f"{source_id} ({class_name})"
            
            for issue in source_issues:
                if "混合使用" in issue["问题"]:
                    problem_groups["混合缓存"].append(source_info)
                elif "不共享" in issue["问题"]:
                    problem_groups["缓存不共享"].append(source_info)
                elif "不使用缓存" in issue["问题"] or "无效" in issue["问题"]:
                    problem_groups["缓存不生效"].append(source_info)
                else:
                    problem_groups["其他问题"].append(source_info)
        
        # 生成建议
        logger.info("1. 缓存统一建议:")
        if problem_groups["混合缓存"]:
            logger.info(f"  以下源使用混合缓存，建议统一使用基类缓存字段:")
            for source in problem_groups["混合缓存"]:
                logger.info(f"   - {source}")
        else:
            logger.info("  未发现混合使用缓存的源")
        
        logger.info("\n2. 缓存共享建议:")
        if problem_groups["缓存不共享"]:
            logger.info(f"  以下源的fetch和get_news缓存不共享，建议修改:")
            for source in problem_groups["缓存不共享"]:
                logger.info(f"   - {source}")
        else:
            logger.info("  未发现缓存不共享的问题")
        
        logger.info("\n3. 缓存失效问题:")
        if problem_groups["缓存不生效"]:
            logger.info(f"  以下源的缓存不生效或clear_cache无效，建议修复:")
            for source in problem_groups["缓存不生效"]:
                logger.info(f"   - {source}")
        else:
            logger.info("  未发现缓存不生效的问题")
        
        logger.info("\n4. 通用建议:")
        logger.info("  - 使用NewsSource基类提供的_cached_news_items和_last_cache_update字段")
        logger.info("  - 确保重写的fetch方法正确使用或更新缓存")
        logger.info("  - 重写clear_cache方法时，确保清理所有缓存相关字段")
        logger.info("  - 定期测试各源的缓存行为，确保性能和稳定性")
        
        return problem_groups
    
    def save_analysis_report(self, method_analysis, field_analysis, cache_test_results, 
                           shared_cache_analysis, issues, recommendations):
        """保存分析报告"""
        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "sources_analyzed": list(self.sources.keys()),
            "method_analysis": method_analysis,
            "field_analysis": field_analysis,
            "cache_test_results": cache_test_results,
            "shared_cache_analysis": shared_cache_analysis,
            "issues": issues,
            "recommendations": {
                k: list(v) for k, v in recommendations.items()
            }
        }
        
        # 转换为JSON兼容格式
        def json_serializer(obj):
            if isinstance(obj, (datetime.datetime, datetime.date)):
                return obj.isoformat()
            try:
                return vars(obj)
            except TypeError:
                return str(obj)
        
        # 保存JSON报告
        with open("source_cache_analysis_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=json_serializer)
        
        logger.info(f"分析报告已保存到 source_cache_analysis_report.json")

async def main():
    """主函数"""
    logger.info("开始分析特定新闻源的缓存机制")
    
    analyzer = SourceAnalyzer(TARGET_SOURCES)
    await analyzer.load_sources()
    
    # 运行分析
    method_analysis = analyzer.analyze_cache_methods()
    field_analysis = analyzer.analyze_cache_fields()
    shared_cache = analyzer.analyze_shared_cache_usage()
    cache_tests = await analyzer.test_caching_behavior()
    
    # 分析问题和生成建议
    issues = analyzer.check_for_issues(method_analysis, field_analysis, cache_tests, shared_cache)
    recommendations = analyzer.generate_recommendations(issues)
    
    # 保存报告
    analyzer.save_analysis_report(method_analysis, field_analysis, cache_tests, 
                               shared_cache, issues, recommendations)
    
    logger.info("特定新闻源缓存机制分析完成")

if __name__ == "__main__":
    asyncio.run(main()) 