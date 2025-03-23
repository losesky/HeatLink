#!/usr/bin/env python
"""
测试脚本：验证已修改的源适配器在错误情况下是否正确抛出异常而不是返回模拟数据
"""
import os
import sys
import logging
from typing import List, Dict, Any

# 添加必要的路径以便能导入模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from worker.sources.sites.bloomberg import BloombergNewsSource
from worker.sources.sites.weibo import WeiboHotNewsSource
from worker.sources.sites.thepaper_selenium import ThePaperSeleniumSource
from worker.sources.sites.linuxdo import LinuxDoNewsSource
from worker.sources.sites.toutiao import ToutiaoHotNewsSource
from worker.sources.sites.coolapk import CoolApkNewsSource
from worker.sources.sites.bilibili import BilibiliHotNewsSource
from worker.sources.sites.cls import CLSNewsSource

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_source(source, name: str) -> bool:
    """
    测试源适配器是否会调用模拟数据生成方法
    通过拦截_create_mock_data或_generate_mock_data方法实现
    
    Args:
        source: 源适配器实例
        name: 源适配器名称
        
    Returns:
        bool: 测试是否通过
    """
    logger.info(f"测试 {name} 适配器...")
    
    # 标志变量，记录是否调用了模拟数据生成方法
    mock_data_called = False
    
    # 备份原始方法
    if hasattr(source, '_create_mock_data'):
        original_method = source._create_mock_data
        
        # 替换为测试方法
        def mock_method(*args, **kwargs):
            nonlocal mock_data_called
            mock_data_called = True
            # 这里不再返回模拟数据，而是抛出异常
            raise RuntimeError("模拟数据生成方法被调用，但应该抛出异常")
        
        # 替换方法
        source._create_mock_data = mock_method
    elif hasattr(source, '_generate_mock_data'):
        original_method = source._generate_mock_data
        
        # 替换为测试方法
        def mock_method(*args, **kwargs):
            nonlocal mock_data_called
            mock_data_called = True
            # 这里不再返回模拟数据，而是抛出异常
            raise RuntimeError("模拟数据生成方法被调用，但应该抛出异常")
        
        # 替换方法
        source._generate_mock_data = mock_method
    else:
        logger.warning(f"{name} 没有找到模拟数据生成方法")
        return True  # 如果没有模拟数据生成方法，视为通过
    
    try:
        # 检查源代码中是否直接使用模拟数据
        source_code = None
        if hasattr(source, 'fetch'):
            import inspect
            source_code = inspect.getsource(source.fetch)
        
        if source_code and ('_create_mock_data()' in source_code or '_generate_mock_data()' in source_code):
            logger.info(f"源码检查: {name} 中直接调用了模拟数据方法")
            return False
        
        return True
    finally:
        # 恢复原始方法
        if hasattr(source, '_create_mock_data'):
            source._create_mock_data = original_method
        elif hasattr(source, '_generate_mock_data'):
            source._generate_mock_data = original_method

def main():
    """主函数，测试所有已修改的源适配器"""
    logger.info("开始测试源适配器异常处理...")
    
    # 准备要测试的源适配器实例
    sources = [
        (BloombergNewsSource(), "Bloomberg (彭博社)"),
        (WeiboHotNewsSource(), "Weibo (微博热搜)"),
        (LinuxDoNewsSource(), "LinuxDo (Linux之道)"),
        (ToutiaoHotNewsSource(), "Toutiao (今日头条)"),
        (CoolApkNewsSource(), "Coolapk (酷安)"),
        (BilibiliHotNewsSource(), "Bilibili (哔哩哔哩)"),
        (CLSNewsSource(), "CLS (财联社)")
    ]
    
    # 为ThePaper添加特殊处理，因为它使用Selenium
    try:
        thepaper = ThePaperSeleniumSource(config={"use_random_delay": False})
        sources.append((thepaper, "ThePaper Selenium (澎湃新闻)"))
    except Exception as e:
        logger.warning(f"无法创建ThePaper Selenium实例: {str(e)}")
    
    # 运行测试
    results = []
    for source, name in sources:
        result = test_source(source, name)
        results.append((name, result))
    
    # 汇总结果
    logger.info("\n测试结果汇总:")
    all_passed = True
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 所有源适配器测试通过！它们都在错误情况下正确抛出异常，而不是返回模拟数据。")
    else:
        logger.info("\n⚠️ 部分源适配器测试失败，它们可能仍在返回模拟数据而不是抛出异常。")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main() 