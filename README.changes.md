# 热链洞察(HeatLink)系统更新日志

## Celery任务调度系统与新闻源功能同步调整

以下是为了确保Celery任务调度系统与新开发的新闻源功能保持同步所做的修改。

### 1. 添加单源自适应调度任务

在`worker/tasks/__init__.py`中，我们添加了新的单源调度任务，该任务每5分钟运行一次，检查哪些源需要更新，并为它们单独创建任务：

```python
# 新增：单源调度任务 - 每5分钟检查一次需要更新的源
sender.add_periodic_task(
    300.0,  # 5分钟
    news.schedule_source_updates.s(),
    name="schedule_source_updates",
    queue="news-queue"
)
```

同时在`celery_app.conf.beat_schedule`配置中也添加了相应的配置。

### 2. 实现单源调度任务

在`worker/tasks/news.py`中，实现了新的`schedule_source_updates`任务：

```python
@celery_app.task(bind=True, name="news.schedule_source_updates")
def schedule_source_updates(self: Task) -> Dict[str, Any]:
    """
    检查并调度需要更新的源
    基于自适应调度器的结果决定哪些源需要更新
    """
    # 实现逻辑...
```

该任务会检查每个源的`should_update`方法返回结果，只为需要更新的源创建单独的抓取任务，从而实现自适应调度。

### 3. 优化`fetch_source_news`任务

对`fetch_source_news`任务进行了优化：

1. 支持任务优先级，基于源的优先级设置
2. 在任务完成后更新源的状态信息到数据库
3. 包括最后更新时间、新闻数量等指标

```python
# 设置任务优先级 (如果支持)
if hasattr(self.request, 'delivery_info') and hasattr(source, 'priority'):
    self.request.delivery_info['priority'] = source.priority

# 更新源的状态信息
db = SessionLocal()
try:
    db_source = get_source(db, source_id)
    if db_source:
        update_data = {
            "last_updated": datetime.utcnow(),
            "news_count": db_source.news_count + saved_count if db_source.news_count else saved_count
        }
        update_source(db, db_obj=db_source, obj_in=update_data)
        db.commit()
        logger.info(f"Updated source status for {source_id}")
# 异常处理...
```

### 4. 增强`_fetch_sources_news`函数

更新了`_fetch_sources_news`函数，在完成抓取后更新源的状态：

```python
# 更新源的状态信息
db = SessionLocal()
try:
    db_source = get_source(db, source.source_id)
    if db_source:
        update_data = {
            "last_updated": datetime.utcnow(),
            "news_count": db_source.news_count + len(result) if db_source.news_count else len(result)
        }
        update_source(db, db_obj=db_source, obj_in=update_data)
        db.commit()
# 异常处理...
```

### 5. 改进`_save_news_to_db`函数

优化了保存新闻到数据库的函数，使用CRUD操作替代直接的数据库操作：

```python
# 检查是否已存在
existing_news = get_news_by_original_id(
    db, source_id=item.source_id, original_id=item.id
)

if existing_news:
    # 更新已有新闻
    news_update = NewsUpdate(
        title=item.title,
        summary=item.summary,
        content=item.content,
        image_url=item.image_url,
        published_at=item.published_at,
        updated_at=datetime.utcnow()
    )
    update_news(db, db_obj=existing_news, obj_in=news_update)
else:
    # 创建新新闻
    news_create = NewsCreate(
        title=item.title,
        url=item.url,
        original_id=item.id,
        source_id=item.source_id,
        summary=item.summary,
        content=item.content,
        image_url=item.image_url,
        published_at=item.published_at
    )
    create_news(db, obj_in=news_create)
    saved_count += 1
```

### 6. 优化`NewsSource`基类

在`worker/sources/base.py`中，增强了`NewsSource`基类的自适应调度功能：

1. 添加了`priority`属性，支持任务优先级
2. 增强了`should_update`方法，支持自适应和固定间隔模式
3. 完善了重试机制，记录错误计数和最后错误信息
4. 改进了性能指标记录，提供更详细的统计信息

```python
def should_update(self) -> bool:
    """
    判断是否应该更新
    基于自适应间隔和最后更新时间
    """
    current_time = time.time()
    
    # 如果从未更新或强制更新，则应该更新
    if self.last_update_time == 0:
        return True
    
    # 计算更新间隔
    interval = self.adaptive_interval if self.enable_adaptive else self.update_interval
    
    # 如果已经过了更新间隔，则应该更新
    return (current_time - self.last_update_time) >= interval
```

### 7. 改进统计数据更新机制

在`worker/stats_wrapper.py`中，改进了统计数据更新机制：

1. 减少默认更新间隔，从3600秒(1小时)减少到900秒(15分钟)
2. 在包装器中记录获取的新闻数量
3. 发生错误时始终更新数据库，不受间隔限制
4. 同时更新源状态和统计信息，确保数据一致性

```python
# 更新源状态
source_status = "active" if success else "error"
if not success and error_message:
    # 记录错误信息
    update_source(db, source_id, {
        "status": source_status,
        "last_error": error_message,
        "error_count": error_count,
        "last_update": current_time
    })
else:
    # 更新状态
    update_source(db, source_id, {
        "status": source_status,
        "last_update": current_time,
        "news_count": stats["news_count"]
    })

# 更新统计信息
update_source_stats(db, source_id, 
                  success_rate=success_rate,
                  avg_response_time=avg_response_time,
                  last_response_time=stats["last_response_time"],
                  total_requests=total_requests,
                  error_count=error_count,
                  news_count=stats["news_count"])
```

## 结论

通过以上修改，我们实现了以下目标：

1. **自适应调度** - 系统现在可以根据数据源的特性动态调整抓取频率
2. **统计数据更新** - 确保每次抓取后正确更新统计数据到数据库
3. **任务优先级** - 支持基于源优先级的任务调度
4. **错误处理** - 增强了错误处理和重试机制
5. **数据一致性** - 确保源状态和统计信息保持一致

这些变更使得Celery任务调度系统能够更好地与新闻源功能协同工作，提高系统整体性能和可靠性。
