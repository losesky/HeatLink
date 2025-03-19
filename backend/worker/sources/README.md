# 数据源开发指南

## 概述

本文档提供了开发新闻数据源的最佳实践和指南。遵循这些指南可以确保数据格式的一致性和代码的可维护性。

## 数据格式

所有数据源必须返回标准化的 `NewsItemModel` 对象，确保以下字段正确设置：

- `id`: 新闻项的唯一标识符
- `title`: 新闻标题
- `url`: 新闻链接
- `source_id`: 数据源ID（必须设置在主体字段中，不要放在extra中）
- `source_name`: 数据源名称（必须设置在主体字段中，不要放在extra中）
- `published_at`: 发布时间
- `updated_at`: 更新时间
- `summary`: 摘要
- `content`: 内容
- `author`: 作者
- `category`: 分类
- `tags`: 标签
- `image_url`: 图片链接
- `language`: 语言
- `country`: 国家
- `extra`: 额外信息（不要在这里放置source_id和source_name）

## 使用 create_news_item 辅助方法

为了确保数据格式的一致性，所有数据源都应该使用 `create_news_item` 辅助方法来创建 `NewsItemModel` 对象。这个方法会：

1. 确保 `source_id` 和 `source_name` 设置在主体字段中
2. 如果 `extra` 字段中包含 `source_id` 或 `source_name`，将它们移除，避免数据重复

示例：

```python
# 正确的方式
news_item = self.create_news_item(
    id=item_id,
    title=title,
    url=url,
    content=content,
    summary=summary,
    image_url=image_url,
    published_at=published_at,
    extra={
        "is_top": False,
        "mobile_url": url,
        "other_info": other_info
    }
)

# 错误的方式（不要这样做）
news_item = NewsItemModel(
    id=item_id,
    title=title,
    url=url,
    content=content,
    summary=summary,
    image_url=image_url,
    published_at=published_at,
    extra={
        "is_top": False,
        "mobile_url": url,
        "source_id": self.source_id,  # 不要在extra中设置source_id
        "source_name": self.name,     # 不要在extra中设置source_name
        "other_info": other_info
    }
)
```

## 数据源开发流程

1. 继承适当的基类（`WebNewsSource`、`APINewsSource`等）
2. 实现必要的方法（`parse_response`、`fetch`等）
3. 使用 `create_news_item` 辅助方法创建 `NewsItemModel` 对象
4. 确保所有必要的字段都正确设置
5. 添加适当的错误处理和日志记录

## 测试和验证

开发新的数据源后，请确保：

1. 运行测试脚本，验证数据源是否正常工作
2. 检查返回的数据格式是否符合要求
3. 验证 `source_id` 和 `source_name` 是否正确设置在主体字段中
4. 确保没有在 `extra` 字段中重复设置 `source_id` 和 `source_name`

## 源统计信息收集

为了监控和评估数据源的性能和可靠性，系统会自动收集每个数据源的统计信息。这些统计信息对于识别问题源、优化资源分配和提高系统整体性能至关重要。

### 统计更新器的工作方式

统计信息通过 `StatsUpdater` 自动收集，该组件会包装数据源的 `fetch` 方法并收集以下指标：

- 请求成功率
- 平均响应时间
- 总请求次数
- 错误次数和最新错误信息

### 如何确保统计信息被收集

为了确保统计信息被正确收集，请遵循以下最佳实践：

1. **使用源管理器**: 始终通过 `NewsSourceManager.fetch_news()` 方法调用数据源，而不是直接调用源的 `fetch` 方法。这是因为统计包装器在源管理器中应用。

```python
# 正确的方式 - 会自动收集统计信息
from worker.sources.manager import source_manager
news = await source_manager.fetch_news('your-source-id')

# 错误的方式 - 不会收集统计信息
from worker.sources.factory import NewsSourceFactory
source = NewsSourceFactory.create_source('your-source-id')
news = await source.fetch()
```

2. **源ID格式一致性**: 源ID在代码和数据库中应保持一致。虽然统计更新器会尝试将下划线格式的ID转换为连字符格式（例如，将 `thepaper_selenium` 转换为 `thepaper-selenium`），但最好在源代码中直接使用与数据库一致的格式。

3. **实现正确的错误处理**: 确保异常被正确捕获和向上传播，以便统计更新器可以记录失败请求。

```python
async def fetch(self):
    try:
        # 获取数据
        response = await self.client.get(self.url)
        # 处理响应
        return self.parse_response(response)
    except Exception as e:
        # 记录错误并重新抛出，允许统计更新器捕获
        logger.error(f"获取数据时出错: {str(e)}")
        raise
```

### 查看源统计信息

可以通过多种方式查看统计信息：

1. **数据库查询**:
```python
from app.db.session import SessionLocal
from app.models.source_stats import SourceStats

db = SessionLocal()
try:
    stats = db.query(SourceStats).filter(
        SourceStats.source_id == 'your-source-id'
    ).order_by(SourceStats.created_at.desc()).first()
    
    if stats:
        print(f"成功率: {stats.success_rate}")
        print(f"平均响应时间: {stats.avg_response_time}ms")
        print(f"总请求次数: {stats.total_requests}")
finally:
    db.close()
```

2. **API查询**:
```
GET /api/sources/stats/{source_id}
```

### 源适配器开发最佳实践

开发新的源适配器时，请遵循以下最佳实践，以确保统计信息可以被正确收集：

1. 正确实现 `fetch` 方法，确保它捕获并向上传播异常
2. 不要直接调用其他源的 `fetch` 方法，而应通过源管理器
3. 在 `get_news` 方法中使用类的 `fetch` 方法，而不是绕过它
4. 保持源ID格式一致，最好使用连字符格式（例如 `thepaper-selenium`）

## 常见问题

### Q: 为什么不能在 extra 中设置 source_id 和 source_name？

A: 这会导致数据格式不一致，使得消费这些数据的代码难以处理。所有数据源都应该以一致的方式设置这些字段，确保它们在主体字段中，而不是 extra 中。

### Q: 如何生成唯一的 ID？

A: 使用 `self.generate_id(url, title, published_at)` 方法生成唯一的 ID。这个方法会基于 URL、标题和发布时间生成一个 MD5 哈希值。

### Q: 如何处理日期和时间？

A: 尽量将日期和时间解析为 `datetime.datetime` 对象，如果无法解析，可以使用 `datetime.datetime.now()` 作为默认值。 