# Redis 缓存集成修复

## 问题描述

在之前的实现中，新闻源数据在 `fetch_source` 方法成功获取后，只更新了 `NewsSource` 类内部的内存缓存（`_cached_news_items`），但未将数据写入 Redis 缓存。这导致了以下问题：

1. `handle_source_news` 和 `handle_news` 等方法尝试从 Redis 中获取数据（使用 `cache_key = f"source:{source_id}"`），但实际上 Redis 中并没有这些数据
2. 即使调用了 `fetch_source` 并成功获取了新闻数据，Redis 缓存也不会被更新
3. 跨实例或重启后的缓存共享无法正常工作

## 修复内容

1. 修改了 `scheduler.py` 中的 `fetch_source` 方法，添加了将新闻条目写入 Redis 缓存的代码：

```python
# 将新闻条目保存到Redis缓存
if self.cache_manager and news_items:
    try:
        cache_key = f"source:{source_id}"
        # 使用源的cache_ttl作为Redis缓存的过期时间
        ttl = getattr(source, 'cache_ttl', 900)  # 默认15分钟
        await self.cache_manager.set(cache_key, news_items, ttl)
        logger.info(f"Saved {len(news_items)} news items to Redis cache with key: {cache_key}, TTL: {ttl}s")
    except Exception as cache_error:
        logger.error(f"Failed to save news items to Redis cache: {str(cache_error)}")
```

2. 创建了测试脚本 `test_redis_cache_integration.py` 来验证修复是否成功

## 运行测试

确保已正确设置 Redis 连接，然后运行测试脚本：

```bash
# 设置 Redis URL 环境变量（如果尚未设置）
export REDIS_URL="redis://localhost:6379/0"

# 测试所有新闻源
python backend/tests/test_redis_cache_integration.py

# 或测试特定的新闻源（例如36kr和ifeng）
python backend/tests/test_redis_cache_integration.py --sources 36kr,ifeng
```

测试脚本会：
1. 清除特定新闻源的 Redis 缓存
2. 调用 `fetch_source` 方法获取新闻数据
3. 验证数据是否正确写入 Redis 缓存
4. 验证缓存的数据格式是否正确

## 验证修复效果

如果测试脚本成功运行并输出类似以下内容，则表示修复成功：

```
Testing news source cache for: 36kr
Successfully fetched data from source: 36kr
Found 30 items in Redis cache for 36kr
Sample cached news item: [标题内容]...
Test result for 36kr: SUCCESS
Test summary: 1/1 sources passed
```

如果测试失败，请检查：
1. Redis 连接是否正常
2. `fetch_source` 方法是否成功获取到新闻数据
3. 缓存写入过程中是否有错误日志

## 注意事项

1. 此修复确保了所有新闻源的数据在获取后会同时更新内存缓存和 Redis 缓存
2. `cache_ttl` 值从源对象获取，默认为 15 分钟（900 秒）
3. 如果 Redis 操作失败，程序会记录错误但不会中断主要的数据获取流程 