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

## 常见问题

### Q: 为什么不能在 extra 中设置 source_id 和 source_name？

A: 这会导致数据格式不一致，使得消费这些数据的代码难以处理。所有数据源都应该以一致的方式设置这些字段，确保它们在主体字段中，而不是 extra 中。

### Q: 如何生成唯一的 ID？

A: 使用 `self.generate_id(url, title, published_at)` 方法生成唯一的 ID。这个方法会基于 URL、标题和发布时间生成一个 MD5 哈希值。

### Q: 如何处理日期和时间？

A: 尽量将日期和时间解析为 `datetime.datetime` 对象，如果无法解析，可以使用 `datetime.datetime.now()` 作为默认值。 