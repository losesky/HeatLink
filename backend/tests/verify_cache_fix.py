#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证缓存修复效果
专门测试ifeng源和36kr源的缓存行为和性能
"""

import os
import sys
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
import datetime
import json
import statistics

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("verify_cache_fix")

# 设置其他模块的日志级别
logging.getLogger("worker").setLevel(logging.DEBUG)  # 使worker模块的日志级别为DEBUG，捕获更多细节

# 为缓存相关日志创建过滤器
class CacheDebugFilter(logging.Filter):
    def filter(self, record):
        # 只保留带有[CACHE-DEBUG]、[BASE-CACHE-INIT]、[IFENG-CACHE-DEBUG]或[36KR-DEBUG]前缀的日志
        return any(prefix in record.getMessage() for prefix in [
            '[CACHE-DEBUG]', 
            '[BASE-CACHE-INIT]', 
            '[IFENG-CACHE-DEBUG]', 
            '[36KR-DEBUG]'
        ])

# 创建缓存调试处理器
cache_debug_handler = logging.FileHandler("cache_debug.log")
cache_debug_handler.setLevel(logging.DEBUG)
cache_debug_handler.addFilter(CacheDebugFilter())
cache_debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
cache_debug_handler.setFormatter(cache_debug_formatter)

# 设置不同的日志记录对象
worker_logger = logging.getLogger("worker")
worker_logger.addHandler(cache_debug_handler)
worker_logger.propagate = False  # 防止日志向上传递

# 设置调试模式
os.environ["DEBUG"] = "1"

# 要测试的新闻源ID
TEST_SOURCES = [
    "ifeng-tech",
    "ifeng-studio",
    "36kr"
]

# 测试配置
TEST_CONFIG = {
    "repeat_count": 3,  # 每个测试重复次数
    "warm_up": True,    # 是否进行预热
    "test_scenarios": [
        "初次获取(force=true)",
        "再次获取(force=false)",
        "强制刷新(force=true)",
        "缓存获取(force=false)",
        "clear_cache后获取"
    ]
}

class CacheVerifier:
    """缓存修复验证器"""
    
    def __init__(self, source_ids):
        self.source_ids = source_ids
        self.sources = {}  # 源ID -> 源实例
        self.results = {}  # 源ID -> 测试结果
    
    async def load_sources(self):
        """加载指定的新闻源"""
        from worker.sources.provider import DefaultNewsSourceProvider
        
        provider = DefaultNewsSourceProvider()
        for source_id in self.source_ids:
            try:
                source = provider.get_source(source_id)
                if source:
                    self.sources[source_id] = source
                    logger.info(f"已加载源: {source_id} (类型: {source.__class__.__name__})")
                else:
                    logger.warning(f"无法加载源: {source_id}")
            except Exception as e:
                logger.error(f"加载源 {source_id} 时出错: {str(e)}")
    
    async def run_tests(self):
        """运行所有测试场景"""
        for source_id, source in self.sources.items():
            logger.info(f"\n=== 开始测试源: {source_id} ===")
            
            # 初始化结果存储
            self.results[source_id] = {
                "源类型": source.__class__.__name__,
                "场景结果": {},
                "结论": {}
            }
            
            # 预热 - 确保源适配器已经初始化
            if TEST_CONFIG["warm_up"]:
                logger.info("预热中...")
                await source.get_news(force_update=True)
                # 等待一会，确保预热完成
                await asyncio.sleep(1)
            
            # 场景1: 首次获取（强制更新）
            timing_data = await self.run_test_scenario(source, "初次获取(force=true)", 
                                                     lambda s: s.get_news(force_update=True))
            self.results[source_id]["场景结果"]["初次获取(force=true)"] = timing_data
            
            # 场景2: 再次获取（不强制更新，应该使用缓存）
            timing_data = await self.run_test_scenario(source, "再次获取(force=false)", 
                                                     lambda s: s.get_news(force_update=False))
            self.results[source_id]["场景结果"]["再次获取(force=false)"] = timing_data
            
            # 检查是否有缓存加速
            fetch1_avg = self.results[source_id]["场景结果"]["初次获取(force=true)"]["平均耗时"]
            fetch2_avg = self.results[source_id]["场景结果"]["再次获取(force=false)"]["平均耗时"]
            cache_speedup = fetch1_avg / max(fetch2_avg, 0.001)
            
            self.results[source_id]["结论"]["缓存加速比"] = cache_speedup
            self.results[source_id]["结论"]["缓存有效"] = cache_speedup > 1.5  # 如果缓存获取至少快50%
            
            logger.info(f"缓存加速比: {cache_speedup:.2f}x - {'有效' if cache_speedup > 1.5 else '无效'}")
            
            # 场景3: 强制刷新
            timing_data = await self.run_test_scenario(source, "强制刷新(force=true)", 
                                                     lambda s: s.get_news(force_update=True))
            self.results[source_id]["场景结果"]["强制刷新(force=true)"] = timing_data
            
            # 场景4: 再次使用缓存
            timing_data = await self.run_test_scenario(source, "缓存获取(force=false)", 
                                                     lambda s: s.get_news(force_update=False))
            self.results[source_id]["场景结果"]["缓存获取(force=false)"] = timing_data
            
            # 检查是否出现了不一致的缓存行为
            fetch3_avg = self.results[source_id]["场景结果"]["强制刷新(force=true)"]["平均耗时"]
            fetch4_avg = self.results[source_id]["场景结果"]["缓存获取(force=false)"]["平均耗时"]
            cache_speedup2 = fetch3_avg / max(fetch4_avg, 0.001)
            
            self.results[source_id]["结论"]["二次缓存加速比"] = cache_speedup2
            self.results[source_id]["结论"]["缓存行为一致"] = abs(cache_speedup - cache_speedup2) < 0.5
            
            logger.info(f"二次缓存加速比: {cache_speedup2:.2f}x")
            logger.info(f"缓存行为一致性: {'良好' if self.results[source_id]['结论']['缓存行为一致'] else '不一致'}")
            
            # 场景5: 清除缓存后再获取
            if hasattr(source, "clear_cache"):
                # 先确保缓存有数据
                await source.get_news(force_update=True)
                
                # 清除缓存
                logger.info("清除缓存...")
                await source.clear_cache()
                
                # 再次获取（应该比使用缓存慢）
                timing_data = await self.run_test_scenario(source, "clear_cache后获取", 
                                                         lambda s: s.get_news(force_update=False))
                self.results[source_id]["场景结果"]["clear_cache后获取"] = timing_data
                
                # 检查清除缓存是否有效
                fetch5_avg = self.results[source_id]["场景结果"]["clear_cache后获取"]["平均耗时"]
                clear_cache_effective = fetch5_avg > fetch4_avg * 1.3  # 如果清除缓存后，获取明显变慢
                
                self.results[source_id]["结论"]["清除缓存有效"] = clear_cache_effective
                logger.info(f"清除缓存有效性: {'有效' if clear_cache_effective else '无效'}")
            else:
                logger.warning(f"源 {source_id} 不支持clear_cache方法")
                self.results[source_id]["结论"]["清除缓存有效"] = None
            
            # 总结源的缓存行为
            results = self.results[source_id]["结论"]
            if results["缓存有效"] and results.get("清除缓存有效", True) and results["缓存行为一致"]:
                overall = "优秀"
            elif results["缓存有效"] and results["缓存行为一致"]:
                overall = "良好"
            elif results["缓存有效"]:
                overall = "一般"
            else:
                overall = "有问题"
                
            self.results[source_id]["结论"]["整体评价"] = overall
            logger.info(f"源 {source_id} 的缓存表现: {overall}")
    
    async def run_test_scenario(self, source, scenario_name, test_function):
        """运行单个测试场景多次并收集时间数据"""
        logger.info(f"测试场景: {scenario_name}")
        
        times = []
        news_counts = []
        
        # 运行多次测试
        for i in range(TEST_CONFIG["repeat_count"]):
            start_time = time.time()
            news = await test_function(source)
            elapsed = time.time() - start_time
            
            times.append(elapsed)
            news_counts.append(len(news) if news else 0)
            
            logger.info(f"  第{i+1}次: 获取到 {len(news) if news else 0} 条新闻，耗时 {elapsed:.3f} 秒")
        
        # 计算统计数据
        avg_time = statistics.mean(times)
        if len(times) > 1:
            std_dev = statistics.stdev(times)
        else:
            std_dev = 0
            
        avg_count = statistics.mean(news_counts)
        
        logger.info(f"  平均耗时: {avg_time:.3f} 秒, 标准差: {std_dev:.3f}, 平均新闻数: {avg_count:.1f}")
        
        return {
            "耗时列表": times,
            "平均耗时": avg_time,
            "标准差": std_dev,
            "新闻数": news_counts,
            "平均新闻数": avg_count
        }
    
    def save_results(self):
        """保存测试结果到文件"""
        output = {
            "测试时间": datetime.datetime.now().isoformat(),
            "测试配置": TEST_CONFIG,
            "测试结果": self.results
        }
        
        with open("cache_verification_results.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"测试结果已保存到 cache_verification_results.json")
    
    def generate_report(self):
        """生成测试报告"""
        logger.info("\n=== 测试总结 ===")
        
        table_data = []
        headers = ["源ID", "类型", "缓存加速", "缓存有效", "清除有效", "一致性", "评价"]
        
        for source_id, result in self.results.items():
            conclusions = result["结论"]
            row = [
                source_id,
                result["源类型"],
                f"{conclusions.get('缓存加速比', 0):.2f}x",
                "是" if conclusions.get("缓存有效", False) else "否",
                "是" if conclusions.get("清除缓存有效", None) else ("否" if conclusions.get("清除缓存有效") is False else "未测试"),
                "是" if conclusions.get("缓存行为一致", False) else "否",
                conclusions.get("整体评价", "未知")
            ]
            table_data.append(row)
        
        # 打印表格
        self.print_table(headers, table_data)
        
        # 建议
        logger.info("\n缓存优化建议:")
        
        for source_id, result in self.results.items():
            conclusions = result["结论"]
            if conclusions.get("整体评价") not in ["优秀", "良好"]:
                logger.info(f"源 {source_id} ({result['源类型']}):")
                
                if not conclusions.get("缓存有效", False):
                    logger.info("  - 缓存无效，可能需要检查get_news和fetch方法中的缓存使用逻辑")
                
                if not conclusions.get("清除缓存有效", True):
                    logger.info("  - 清除缓存无效，可能需要检查clear_cache方法是否正确清理所有缓存字段")
                
                if not conclusions.get("缓存行为一致", False):
                    logger.info("  - 缓存行为不一致，可能存在条件性缓存逻辑，建议检查")
    
    def print_table(self, headers, rows):
        """打印格式化表格"""
        # 计算每列宽度
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # 打印表头
        header_str = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        logger.info(header_str)
        logger.info("-" * len(header_str))
        
        # 打印数据行
        for row in rows:
            row_str = " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
            logger.info(row_str)

async def main():
    """主函数"""
    logger.info("开始验证缓存修复效果")
    
    verifier = CacheVerifier(TEST_SOURCES)
    await verifier.load_sources()
    await verifier.run_tests()
    verifier.save_results()
    verifier.generate_report()
    
    logger.info("验证完成")

if __name__ == "__main__":
    asyncio.run(main()) 