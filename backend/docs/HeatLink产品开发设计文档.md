# 热链洞察 (HeatLink) 产品开发设计文档

## 1. 产品概述

热链洞察（HeatLink）是一个高度可扩展的多源新闻聚合平台，能够从30+不同来源实时收集、处理和聚合新闻数据，包括社交媒体热搜、新闻网站、技术社区等。系统通过智能分析和处理，为用户提供个性化、多维度的新闻阅读体验。

## 2. 技术架构

### 2.1 总体架构

系统采用分层架构设计，主要包括：
- 前端应用层：基于React的用户界面
- API网关层：处理认证、限流、路由等
- 核心服务层：基于FastAPI实现的微服务集群
- 数据采集层：多源数据采集与处理
- 数据存储层：PostgreSQL和Redis
- 消息队列层：基于Celery和RabbitMQ的任务调度

### 2.2 技术栈

- **前端**：React, Ant Design, Redux, TypeScript
- **后端**：FastAPI, Pydantic, SQLAlchemy, Alembic
- **数据库**：PostgreSQL (结构化数据), Redis (缓存)
- **任务队列**：Celery, RabbitMQ
- **容器化**：Docker, Kubernetes
- **监控**：Prometheus, Grafana

## 3. 核心功能模块

### 3.1 多源数据采集架构

#### 3.1.1 数据源适配器设计

系统实现了统一的数据源接口，并开发了三种主要的适配器类型：

1. **API新闻源适配器 (APISource)**
   - 负责从提供API的新闻源获取数据
   - 支持自定义请求头、查询参数和响应映射
   - 支持嵌套JSON路径解析

2. **Web新闻源适配器 (WebSource)**
   - 负责从网页解析结构化内容
   - 使用CSS选择器提取内容
   - 支持HTML属性和元素内容提取

3. **RSS新闻源适配器 (RSSSource)**
   - 负责解析RSS/Atom格式的新闻源
   - 自动处理发布日期、作者等标准字段
   - 支持多种RSS格式版本

#### 3.1.2 数据源管理

```python
class NewsSource(ABC):
    """新闻源基类"""
    
    def __init__(
        self, 
        source_id: str, 
        name: str, 
        update_interval: int = 600,
        cache_ttl: int = 300,
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: Optional[str] = None
    ):
        # 初始化属性
        
    @abstractmethod
    async def fetch(self) -> List[NewsItemModel]:
        """获取新闻数据"""
        pass
    
    async def process(self) -> List[NewsItemModel]:
        """处理新闻数据流程"""
        # 检查缓存
        # 获取新数据
        # 更新缓存
        # 记录最后抓取时间
```

#### 3.1.3 数据源工厂模式

实现了工厂模式，用于创建和管理不同类型的数据源：

```python
class NewsSourceFactory:
    @staticmethod
    def create_source(source_type: str, **kwargs) -> Optional[NewsSource]:
        """根据源类型创建具体的数据源实例"""
        # 根据类型返回对应的数据源实例
        
    @staticmethod
    def get_available_sources() -> List[str]:
        """获取所有可用的数据源类型"""
        # 返回已注册的数据源类型列表
```

### 3.2 分级自动更新机制

#### 3.2.1 基于Celery的任务调度

系统使用Celery框架实现分布式任务队列，主要任务包括：

1. **高频更新任务**
   - 每10分钟执行一次
   - 主要处理社交媒体热搜等实时性强的源
   - 任务队列优先级最高

2. **中频更新任务**
   - 每30分钟执行一次
   - 处理新闻网站等中等频率更新的源

3. **低频更新任务**
   - 每60分钟执行一次
   - 处理博客、周刊等更新不频繁的源

4. **维护任务**
   - 每天凌晨3点清理过期新闻（默认30天前）
   - 每周日凌晨4点进行数据分析和聚合

```python
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """设置周期性任务"""
    # 高频更新源（每10分钟）
    sender.add_periodic_task(
        600.0,
        news.fetch_high_frequency_sources.s(),
        name="fetch_high_frequency_sources",
        queue="news-queue"
    )
    
    # 中频更新源（每30分钟）
    sender.add_periodic_task(
        1800.0,
        news.fetch_medium_frequency_sources.s(),
        name="fetch_medium_frequency_sources",
        queue="news-queue"
    )
    
    # 低频更新源（每小时）
    sender.add_periodic_task(
        3600.0,
        news.fetch_low_frequency_sources.s(),
        name="fetch_low_frequency_sources",
        queue="news-queue"
    )
    
    # 清理过期新闻（每天）
    sender.add_periodic_task(
        crontab(minute=0, hour=3),
        news.cleanup_old_news.s(days=30),
        name="cleanup_old_news_daily",
        queue="news-queue"
    )
    
    # 数据分析和聚合（每周）
    sender.add_periodic_task(
        crontab(minute=0, hour=4, day_of_week=0),
        news.analyze_news_trends.s(days=7),
        name="analyze_news_trends_weekly",
        queue="news-queue"
    )
```

#### 3.2.2 任务实现

以高频更新任务为例：

```python
@celery_app.task(bind=True, name="news.fetch_high_frequency_sources")
def fetch_high_frequency_sources(self: Task) -> Dict[str, Any]:
    """
    获取高频更新的新闻源（每10分钟）
    主要是社交媒体等实时性较强的源
    """
    logger.info("Starting high frequency news fetch task")
    
    try:
        # 获取所有高频更新的新闻源（更新间隔小于等于15分钟）
        sources = [
            source for source in source_manager.get_all_sources()
            if source.update_interval <= 900  # 15分钟 = 900秒
        ]
        
        # 获取所有高频源的新闻
        results = asyncio.run(_fetch_sources_news(sources))
        
        return {
            "status": "success",
            "message": f"Fetched news from {len(results)} high frequency sources",
            "sources": [source.source_id for source in sources],
            "total_news": sum(len(news) for news in results.values())
        }
    except Exception as e:
        logger.error(f"Error in high frequency news fetch task: {str(e)}")
        return {"status": "error", "message": str(e)}
```

### 3.3 自适应调度器

自适应调度器（AdaptiveScheduler）是系统的核心组件之一，能够根据数据源特性和实时情况动态调整抓取策略。

#### 3.3.1 核心设计

```python
class AdaptiveScheduler:
    """
    自适应调度器
    根据数据源的更新频率和重要性动态调整抓取任务的执行频率
    """
    
    def __init__(
        self,
        cache_manager: CacheManager,
        min_interval: int = 120,  # 最小抓取间隔，单位秒，默认2分钟
        max_interval: int = 3600,  # 最大抓取间隔，单位秒，默认1小时
        enable_adaptive: bool = True,  # 是否启用自适应调度
        enable_cache: bool = True,  # 是否启用缓存
    ):
        # 初始化成员变量
        
    def should_fetch(self, source_id: str) -> bool:
        """
        判断是否应该抓取数据源
        """
        # 判断逻辑
        
    async def fetch_source(self, source_id: str, force: bool = False) -> bool:
        """
        抓取数据源
        """
        # 抓取实现
        
    def adjust_interval(self, source_id: str, result: Dict[str, Any]):
        """
        根据抓取结果调整抓取间隔
        """
        # 调整算法
```

#### 3.3.2 动态调整策略

1. **更新频率评分**：根据历史数据变化情况评估数据源更新频率
2. **成功率影响**：抓取失败次数增加时降低优先级
3. **响应时间考量**：响应时间过长的源适当降低频率
4. **内容变化率**：根据内容变化频率调整抓取频率

### 3.4 数据缓存机制

系统实现了多级缓存策略，有效减少重复请求和提高响应速度。

#### 3.4.1 缓存管理器

```python
class CacheManager:
    """
    缓存管理器
    负责管理系统中所有缓存相关操作
    """
    
    def __init__(self, redis_url: str = None):
        """初始化缓存管理器"""
        # 初始化Redis连接
        
    async def get_cached_news(self, source_id: str) -> Optional[List[Dict]]:
        """获取缓存的新闻数据"""
        # 获取缓存
        
    async def cache_news(self, source_id: str, news_items: List[NewsItemModel], ttl: int = None):
        """缓存新闻数据"""
        # 设置缓存
        
    async def invalidate_cache(self, source_id: str):
        """使缓存失效"""
        # 删除缓存
```

#### 3.4.2 缓存策略

1. **分层缓存**：API响应、解析结果和处理后数据分别缓存
2. **自定义TTL**：不同数据源设置不同的缓存过期时间
3. **条件缓存**：根据响应状态和内容决定是否缓存
4. **缓存预热**：系统启动时预加载关键数据
5. **缓存失效策略**：主动和被动两种失效机制

### 3.5 数据处理和存储

#### 3.5.1 数据模型设计

系统设计了完整的数据模型，主要包括：

1. **新闻源模型 (Source)**
   ```python
   class Source(Base):
       __tablename__ = "sources"
       
       id = Column(String(50), primary_key=True)
       name = Column(String(100), nullable=False)
       description = Column(Text, nullable=True)
       url = Column(String(512), nullable=True)
       type = Column(Enum(SourceType), nullable=False)
       active = Column(Boolean, default=True)
       update_interval = Column(Interval, default=timedelta(minutes=10))
       cache_ttl = Column(Interval, default=timedelta(minutes=5))
       # 其他字段...
   ```

2. **新闻模型 (News)**
   ```python
   class News(Base):
       __tablename__ = "news"
       
       id = Column(Integer, primary_key=True, index=True)
       title = Column(String(255), nullable=False)
       url = Column(String(512), nullable=False)
       original_id = Column(String(255), nullable=False)
       source_id = Column(String(50), ForeignKey("sources.id"), nullable=False)
       category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
       content = Column(Text, nullable=True)
       # 其他字段...
   ```

3. **分类模型 (Category)**
4. **标签模型 (Tag)**
5. **用户模型 (User)**

#### 3.5.2 数据处理流程

1. **数据获取**：从数据源获取原始数据
2. **数据解析**：根据配置解析结构化数据
3. **数据标准化**：统一不同来源的数据格式
4. **数据清洗**：去除HTML标签、修正格式错误等
5. **数据去重**：检测并合并重复内容
6. **数据存储**：将处理后的数据保存到数据库

```python
async def process_news_item(db: Session, source: Source, item: NewsItemModel) -> Optional[News]:
    """处理单个新闻项目"""
    # 检查是否已存在（去重）
    existing_news = get_news_by_original_id(db, source_id=source.id, original_id=item.id)
    
    if existing_news:
        # 更新已有的新闻（如有变化）
        if _should_update_news(existing_news, item):
            news_update = NewsUpdate(
                title=item.title,
                content=item.content,
                # 其他更新字段...
            )
            return update_news(db, news_id=existing_news.id, news_in=news_update)
        return existing_news
    
    # 创建新的新闻项目
    news_create = NewsCreate(
        title=item.title,
        url=item.url,
        original_id=item.id,
        source_id=source.id,
        # 其他字段...
    )
    return create_news(db, news_in=news_create)
```

### 3.6 数据监控和统计

系统实现了完整的数据源监控功能，帮助运营人员了解系统状态和数据源健康情况。

#### 3.6.1 监控指标

1. **源状态监控**：活跃/错误/警告/非活跃状态
2. **性能监控**：平均响应时间、成功率
3. **数据量监控**：请求总数、错误数量
4. **更新频率**：最后更新时间、实际更新间隔

#### 3.6.2 监控接口

```python
@router.get("/sources", response_model=MonitorResponse)
def get_source_monitor_data(
    status: Optional[SourceStatus] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(deps.get_db)
):
    """
    获取新闻源监控数据
    """
    # 实现逻辑
```

#### 3.6.3 统计功能

1. **源性能统计**：各时段成功率、响应时间等
2. **高峰期分析**：访问高峰期识别
3. **错误分析**：常见错误类型和原因
4. **数据量趋势**：各时段数据量变化

### 3.7 定期维护机制

系统实现了自动化的定期维护机制，确保长期稳定运行。

#### 3.7.1 过期数据清理

```python
@celery_app.task(bind=True, name="news.cleanup_old_news")
def cleanup_old_news(self: Task, days: int = 30) -> Dict[str, Any]:
    """
    清理过期新闻数据
    """
    logger.info(f"Starting cleanup task for news older than {days} days")
    
    try:
        db = SessionLocal()
        try:
            # 计算截止日期
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # 获取要删除的新闻ID
            news_to_delete = db.query(News).filter(News.published_at < cutoff_date)
            count = news_to_delete.count()
            
            if count > 0:
                # 先删除关联表中的记录
                news_ids = [news.id for news in news_to_delete]
                
                # 删除新闻本身
                news_to_delete.delete(synchronize_session=False)
                
                db.commit()
                logger.info(f"Deleted {count} old news items")
            else:
                logger.info(f"No news older than {days} days found")
            
            return {
                "status": "success",
                "message": f"Cleanup completed. Deleted {count} old news items.",
                "deleted_count": count
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in cleanup task: {str(e)}")
        return {"status": "error", "message": str(e)}
```

#### 3.7.2 数据分析和聚合

```python
@celery_app.task(bind=True, name="news.analyze_news_trends")
def analyze_news_trends(self: Task, days: int = 7) -> Dict[str, Any]:
    """
    分析新闻趋势
    """
    logger.info(f"Starting news trend analysis for the past {days} days")
    
    try:
        # 实现分析逻辑...
        
        return {
            "status": "success",
            "message": "News trend analysis completed",
            # 分析结果...
        }
    except Exception as e:
        logger.error(f"Error in news trend analysis: {str(e)}")
        return {"status": "error", "message": str(e)}
```

## 4. 非功能性需求实现

### 4.1 性能优化

1. **连接池**：数据库和Redis连接池
2. **异步IO**：使用asyncio实现非阻塞操作
3. **批量处理**：批量插入和更新数据
4. **索引优化**：针对查询模式优化数据库索引

### 4.2 可靠性设计

1. **重试机制**：网络请求失败自动重试
2. **熔断器**：防止级联故障
3. **错误恢复**：任务执行失败后的恢复策略
4. **日志记录**：详细的错误和警告日志

### 4.3 可扩展性设计

1. **模块化架构**：松耦合的组件设计
2. **插件系统**：支持动态加载新的数据源适配器
3. **配置化**：大部分功能通过配置文件调整，无需修改代码
4. **水平扩展**：支持多实例部署

## 5. 部署架构

系统采用Docker容器化部署，主要组件包括：

1. **应用服务器**：运行FastAPI应用
2. **Worker节点**：运行Celery工作节点
3. **消息代理**：RabbitMQ服务
4. **数据库服务**：PostgreSQL
5. **缓存服务**：Redis

```yaml
# docker-compose.yml 主要服务
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    # 配置...

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    # 配置...

  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile.worker
    # 配置...

  postgres:
    image: postgres:13
    # 配置...

  redis:
    image: redis:6
    # 配置...

  rabbitmq:
    image: rabbitmq:3-management
    # 配置...
```

## 6. 测试策略

1. **单元测试**：针对关键功能模块的测试
2. **集成测试**：验证组件间交互
3. **性能测试**：验证系统在高负载下的表现
4. **健壮性测试**：验证系统在异常情况下的恢复能力

## 7. 运维支持

1. **监控仪表板**：Grafana仪表板展示系统状态
2. **告警系统**：异常情况自动告警
3. **日志管理**：集中式日志收集和分析
4. **备份策略**：定期数据备份和恢复测试

## 8. 后续规划

1. **内容聚类和聚合**：实现相似内容的智能聚合
2. **个性化推荐**：基于用户行为的内容推荐
3. **NLP分析**：情感分析、关键词提取等高级功能
4. **用户交互功能**：收藏、订阅等用户交互功能

## 9. 结论

热链洞察（HeatLink）已经实现了稳健的多源数据采集、分级自动更新、自适应调度、数据缓存、数据处理和存储、数据监控和定期维护等核心功能，为后续功能扩展奠定了坚实基础。系统架构具有高度的灵活性和可扩展性，能够适应不断变化的需求和数据源。 