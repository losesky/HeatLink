"""
缓存增强器模块测试
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch

from backend.worker.utils.cache_enhancer import (
    enhance_source, 
    CacheMetrics, 
    CacheProtectionStats,
    CacheEnhancer,
    cache_enhanced,
    CacheMonitor,
    cache_monitor
)

# 创建一个模拟的新闻源类
class MockNewsSource:
    def __init__(self, source_id, name, update_interval=600, cache_ttl=900):
        self.source_id = source_id
        self.name = name
        self.update_interval = update_interval
        self.cache_ttl = cache_ttl
        self._cached_news_items = []
        self._last_cache_update = 0
        
    async def fetch(self):
        # 模拟获取新闻
        return [{"title": f"新闻 {i}", "content": f"内容 {i}"} for i in range(10)]
    
    async def get_news(self, force_update=False):
        # 默认实现
        if force_update or not self.is_cache_valid():
            news_items = await self.fetch()
            await self.update_cache(news_items)
            return news_items
        return self._cached_news_items
    
    def is_cache_valid(self):
        # 检查缓存是否有效
        if not self._cached_news_items:
            return False
        cache_age = time.time() - self._last_cache_update
        return cache_age < self.cache_ttl
    
    async def update_cache(self, news_items):
        # 更新缓存
        if news_items:
            self._cached_news_items = news_items
            self._last_cache_update = time.time()
    
    async def clear_cache(self):
        # 清除缓存
        self._cached_news_items = []
        self._last_cache_update = 0

# 错误新闻源: 模拟fetch失败的情况
class ErrorNewsSource(MockNewsSource):
    async def fetch(self):
        # 模拟获取失败
        raise Exception("模拟的网络错误")

# 空结果新闻源: 模拟返回空列表的情况
class EmptyNewsSource(MockNewsSource):
    async def fetch(self):
        # 模拟返回空列表
        return []

# 数据减少新闻源: 模拟数据量大幅减少的情况
class ShrinkNewsSource(MockNewsSource):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fetch_count = 0
        
    async def fetch(self):
        self._fetch_count += 1
        # 第一次返回20条，后续返回3条
        if self._fetch_count == 1:
            return [{"title": f"新闻 {i}", "content": f"内容 {i}"} for i in range(20)]
        else:
            return [{"title": f"新闻 {i}", "content": f"内容 {i}"} for i in range(3)]

@pytest.fixture
def mock_source():
    return MockNewsSource("test", "测试源")

@pytest.fixture
def error_source():
    return ErrorNewsSource("error_test", "错误测试源")

@pytest.fixture
def empty_source():
    return EmptyNewsSource("empty_test", "空结果测试源")

@pytest.fixture
def shrink_source():
    return ShrinkNewsSource("shrink_test", "数据减少测试源")

# 测试基本的缓存增强功能
@pytest.mark.asyncio
async def test_enhance_source_basic(mock_source):
    # 增强源
    enhanced = enhance_source(mock_source)
    
    # 确认增强成功
    assert enhanced is mock_source
    assert hasattr(mock_source, '_cache_enhanced')
    assert mock_source._cache_enhanced is True
    assert hasattr(mock_source, '_cache_metrics')
    assert hasattr(mock_source, '_cache_protection_stats')
    
    # 测试get_news方法被增强
    assert mock_source.get_news != MockNewsSource.get_news
    
    # 测试cache_status方法被添加
    assert hasattr(mock_source, 'cache_status')
    assert callable(mock_source.cache_status)

# 测试缓存增强的方法包装
@pytest.mark.asyncio
async def test_enhanced_get_news(mock_source):
    # 增强源
    enhanced = enhance_source(mock_source)
    
    # 测试强制更新
    news = await enhanced.get_news(force_update=True)
    assert len(news) == 10
    assert enhanced._cache_metrics.cache_miss_count == 1
    assert enhanced._cache_metrics.cache_hit_count == 0
    
    # 测试缓存命中
    news = await enhanced.get_news()
    assert len(news) == 10
    assert enhanced._cache_metrics.cache_miss_count == 1
    assert enhanced._cache_metrics.cache_hit_count == 1
    
    # 查看缓存状态
    status = enhanced.cache_status()
    assert status['source_id'] == 'test'
    assert status['source_name'] == '测试源'
    assert status['cache_state']['items_count'] == 10
    assert status['cache_state']['valid'] is True

# 测试空结果保护
@pytest.mark.asyncio
async def test_empty_result_protection(empty_source):
    # 增强源
    enhanced = enhance_source(empty_source)
    
    # 先用正常数据填充缓存
    with patch.object(empty_source, 'fetch', 
                     return_value=[{"title": f"新闻 {i}"} for i in range(5)]):
        await enhanced.get_news(force_update=True)
    
    assert len(enhanced._cached_news_items) == 5
    
    # 测试空结果保护
    news = await enhanced.get_news(force_update=True)
    assert len(news) == 5  # 保护生效，仍返回缓存的5条
    assert enhanced._cache_protection_stats.empty_protection_count == 1
    
    status = enhanced.cache_status()
    assert status['protection_stats']['empty_protection_count'] == 1

# 测试错误保护
@pytest.mark.asyncio
async def test_error_protection(error_source):
    # 增强源
    enhanced = enhance_source(error_source)
    
    # 先用正常数据填充缓存
    with patch.object(error_source, 'fetch', 
                     return_value=[{"title": f"新闻 {i}"} for i in range(5)]):
        await enhanced.get_news(force_update=True)
    
    assert len(enhanced._cached_news_items) == 5
    
    # 测试错误保护
    news = await enhanced.get_news(force_update=True)
    assert len(news) == 5  # 保护生效，仍返回缓存的5条
    assert enhanced._cache_protection_stats.error_protection_count == 1
    
    status = enhanced.cache_status()
    assert status['protection_stats']['error_protection_count'] == 1

# 测试数据减少保护
@pytest.mark.asyncio
async def test_shrink_protection(shrink_source):
    # 增强源
    enhanced = enhance_source(shrink_source)
    
    # 第一次获取，填充20条数据
    news = await enhanced.get_news(force_update=True)
    assert len(news) == 20
    
    # 第二次获取，fetch会返回3条数据，但保护机制生效
    news = await enhanced.get_news(force_update=True)
    assert len(news) == 20  # 保护生效，仍使用20条数据
    assert enhanced._cache_protection_stats.shrink_protection_count == 1
    
    status = enhanced.cache_status()
    assert status['protection_stats']['shrink_protection_count'] == 1
    
    # 检查保护历史
    history = enhanced._cache_protection_stats.protection_history
    assert len(history) > 0
    assert history[-1]['type'] == 'shrink_protection'
    assert history[-1]['old_size'] == 20
    assert history[-1]['new_size'] == 3

# 测试装饰器功能
@cache_enhanced
class EnhancedSource(MockNewsSource):
    pass

@pytest.mark.asyncio
async def test_cache_enhanced_decorator():
    source = EnhancedSource("decorated", "装饰器测试源")
    
    # 确认在初始化时已被增强
    assert hasattr(source, '_cache_enhanced')
    assert source._cache_enhanced is True
    
    # 测试功能
    news = await source.get_news(force_update=True)
    assert len(news) == 10
    assert source._cache_metrics.cache_miss_count == 1

# 测试CacheMonitor功能
@pytest.mark.asyncio
async def test_cache_monitor():
    # 获取单例
    monitor = CacheMonitor.get_instance()
    assert monitor is cache_monitor
    
    # 注册不同类型的源
    sources = {
        "normal": MockNewsSource("normal", "正常源"),
        "error": ErrorNewsSource("error", "错误源"),
        "empty": EmptyNewsSource("empty", "空源")
    }
    
    for source_id, source in sources.items():
        monitor.register_source(source)
    
    # 确认所有源都被增强
    assert len(monitor.enhanced_sources) == 3
    for source_id, source in monitor.enhanced_sources.items():
        assert hasattr(source, '_cache_enhanced')
        assert source._cache_enhanced is True
    
    # 测试全局状态
    global_status = monitor.get_global_status()
    assert 'global_metrics' in global_status
    assert 'sources' in global_status
    assert len(global_status['sources']) == 3

# 测试多源场景下的指标聚合
@pytest.mark.asyncio
async def test_multiple_sources_metrics():
    # 清除之前测试的数据
    monitor = CacheMonitor.get_instance()
    monitor.enhanced_sources = {}
    
    # 创建多个源
    sources = {
        "source1": MockNewsSource("source1", "源1"),
        "source2": MockNewsSource("source2", "源2"),
        "source3": ErrorNewsSource("source3", "源3"),
    }
    
    # 注册源
    for source_id, source in sources.items():
        monitor.register_source(source)
    
    # 执行一些操作以生成指标数据
    await sources["source1"].get_news(force_update=True)
    await sources["source1"].get_news()  # 缓存命中
    await sources["source2"].get_news(force_update=True)
    await sources["source3"].get_news(force_update=True)  # 将触发错误保护
    
    # 获取全局状态
    status = monitor.get_global_status()
    
    # 验证指标
    metrics = status['global_metrics']
    assert metrics['total_cache_hits'] >= 1
    assert metrics['total_cache_misses'] >= 3
    assert metrics['total_protections'] >= 1
    assert metrics['protection_breakdown']['error_protections'] >= 1 