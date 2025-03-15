# HeatLink - 多源新闻聚合系统

HeatLink是一个多源新闻聚合系统，可以从多个来源收集新闻和热点信息，并提供统一的访问接口。

## 系统架构

HeatLink采用现代化的微服务架构，主要由以下几个核心组件构成：

1. **API服务**：基于FastAPI构建的RESTful API，提供新闻数据的查询、管理和用户交互功能
2. **Worker服务**：负责后台任务处理，包括新闻抓取、数据处理和定时任务
3. **Beat服务**：Celery Beat调度器，负责定时触发任务
4. **数据库**：PostgreSQL关系型数据库，存储结构化数据
5. **缓存**：Redis缓存服务，提高系统性能并支持任务队列

系统架构图：
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   客户端    │────▶│  API服务    │◀───▶│  数据库     │
└─────────────┘     └──────┬──────┘     └─────────────┘
                          │                    ▲
                          ▼                    │
                    ┌─────────────┐     ┌─────────────┐
                    │  Redis缓存  │◀───▶│ Worker服务  │
                    └─────────────┘     └──────┬──────┘
                          ▲                    │
                          │                    ▼
                          │             ┌─────────────┐
                          └─────────────│  Beat服务   │
                                        └─────────────┘
```

## 核心功能与实现

### 1. 多源新闻聚合

系统支持从多种类型的新闻源获取数据：
- **API源**：通过调用第三方API获取新闻数据
- **网页源**：通过网页爬虫抓取新闻内容
- **RSS源**：解析RSS feed获取新闻更新

每个新闻源都有独立的配置，包括更新间隔、缓存时间、请求参数等。系统通过`Source`模型管理这些配置，并通过工厂模式创建对应的新闻源处理器。

### 2. 自适应调度系统

系统实现了一个智能的自适应调度器（`AdaptiveScheduler`），能够根据以下因素动态调整新闻源的抓取频率：
- 新闻源的更新频率
- 用户访问量
- 系统负载
- 历史错误率

这确保了系统能够在保持数据新鲜度的同时，优化资源使用效率。

### 3. 多级缓存机制

系统采用多级缓存策略提高性能：
- **内存缓存**：用于频繁访问的热点数据
- **Redis缓存**：分布式缓存，支持跨服务共享
- **数据库缓存**：持久化存储

缓存管理器（`CacheManager`）负责缓存的一致性和过期策略，确保用户能够获取最新数据。

### 4. 用户个性化功能

系统支持丰富的用户个性化功能：
- **用户订阅**：订阅特定新闻源、分类或标签
- **收藏功能**：保存感兴趣的新闻
- **阅读历史**：记录用户阅读行为
- **个性化推荐**：基于用户行为的内容推荐

这些功能通过`User`、`Subscription`等模型实现，并通过相应的API端点提供服务。

### 5. 内容分类与聚类

系统具备智能的内容处理能力：
- **分类系统**：通过`Category`和`Tag`模型对新闻进行分类
- **内容聚类**：相似新闻自动聚合，减少信息冗余
- **情感分析**：对新闻内容进行情感评分

### 6. 任务监控与管理

系统提供了全面的任务监控与管理功能：
- **命令行工具**：通过 `run_task.py` 和 `task_status.py` 执行和监控任务
- **Web 监控界面**：使用 Flower 提供实时任务监控
- **API 接口**：提供 RESTful API 执行和查询任务
- **自适应调度**：根据任务执行情况动态调整调度策略

## 数据模型设计

系统的核心数据模型包括：

1. **News**：新闻条目，包含标题、内容、来源、发布时间等信息
2. **Source**：新闻源，定义数据来源及其配置
3. **Category**：新闻分类
4. **Tag**：新闻标签
5. **User**：用户信息
6. **Subscription**：用户订阅关系

模型之间通过外键和多对多关系建立连接，形成完整的数据关系网络。

## API接口设计

系统提供RESTful API，主要包括以下端点：

1. **/api/news**：新闻相关操作
   - GET /：获取新闻列表，支持多种过滤条件
   - GET /{id}：获取特定新闻详情
   - GET /trending：获取热门新闻
   - GET /cluster/{cluster_id}：获取同一聚类的新闻

2. **/api/sources**：新闻源管理
   - GET /：获取所有新闻源
   - POST /：创建新闻源
   - GET /{id}：获取特定新闻源详情
   - PUT /{id}：更新新闻源配置
   - DELETE /{id}：删除新闻源

3. **/api/users**：用户管理
   - GET /me：获取当前用户信息
   - PUT /me：更新用户信息
   - GET /me/favorites：获取收藏列表
   - POST /me/favorites/{news_id}：添加收藏
   - DELETE /me/favorites/{news_id}：取消收藏

4. **/api/auth**：认证相关
   - POST /login：用户登录
   - POST /register：用户注册

5. **/api/tasks**：任务管理
   - POST /run/high-frequency：运行高频更新任务
   - POST /run/medium-frequency：运行中频更新任务
   - POST /run/low-frequency：运行低频更新任务
   - POST /run/all-news：运行所有新闻更新任务
   - POST /run/source-news/{source_id}：运行指定新闻源更新任务
   - GET /status/{task_id}：获取任务状态
   - GET /active：获取活跃任务列表

所有API端点都有完整的OpenAPI文档，可通过Swagger UI或ReDoc访问。

## 后台任务系统

系统使用Celery作为任务队列，处理以下类型的后台任务：

1. **定时抓取任务**：根据配置的时间间隔，定期从各个新闻源获取最新内容
2. **数据处理任务**：内容清洗、分类、聚类、情感分析等
3. **缓存管理任务**：定期清理过期缓存，预热热点数据缓存
4. **系统维护任务**：数据备份、错误监控、性能统计等

任务调度由Celery Beat管理，确保任务按计划执行。系统提供了多种方式监控任务执行状态：

1. **命令行工具**：
   ```bash
   # 执行任务
   python run_task.py high_freq
   
   # 查询任务状态
   python task_status.py <task_id>
   ```

2. **Flower 监控界面**：
   ```bash
   celery -A worker.celery_app flower --port=5555
   ```
   
   访问 http://localhost:5555 查看任务执行情况。

3. **API 接口**：
   ```
   GET /api/tasks/status/{task_id}
   GET /api/tasks/active
   ```

## 开发环境配置

系统提供了完整的本地开发环境配置：

1. **本地开发脚本**：`local-dev.sh`启动所需的基础服务（PostgreSQL、Redis等）
2. **环境变量**：通过`.env.local`文件配置开发环境变量
3. **热重载**：支持代码修改后自动重启服务
4. **调试工具**：集成了各种调试和监控工具

## 部署配置

系统支持多种部署方式，主要基于Docker和Docker Compose：

1. **生产环境**：使用`docker-compose.yml`配置完整的生产环境部署
2. **开发环境**：使用`docker-compose.dev.yml`配置开发环境部署
3. **本地环境**：使用`docker-compose.local.yml`配置本地测试环境

Docker配置包括：
- 应用服务容器（API服务）
- Worker服务容器（后台任务处理）
- Beat服务容器（任务调度）
- PostgreSQL数据库容器
- Redis缓存容器

系统使用健康检查确保服务依赖关系正确启动，并配置了适当的重启策略以提高可靠性。

## 安全性考虑

系统实现了多层次的安全防护：

1. **认证与授权**：基于JWT的用户认证和基于角色的访问控制
2. **数据加密**：敏感数据加密存储
3. **CORS保护**：配置适当的跨域资源共享策略
4. **参数验证**：使用Pydantic模型进行严格的输入验证
5. **防SQL注入**：使用ORM和参数化查询防止SQL注入攻击

## 扩展性设计

系统设计考虑了未来的扩展需求：

1. **模块化架构**：各组件松耦合，便于独立扩展
2. **插件系统**：支持通过插件扩展新闻源和数据处理能力
3. **水平扩展**：支持增加Worker节点处理更多并发任务
4. **API版本控制**：支持API版本管理，确保向后兼容

## 监控与日志

系统集成了完善的监控和日志功能：

1. **应用日志**：详细记录系统运行状态和错误信息
2. **性能指标**：收集关键性能指标，如响应时间、缓存命中率等
3. **健康检查**：定期检查系统各组件的健康状态
4. **告警机制**：异常情况自动触发告警
5. **任务监控**：通过 Flower 和自定义 API 监控任务执行状态

## 快速开始

### 使用Docker Compose

1. 克隆仓库:
   ```bash
   git clone https://github.com/yourusername/heatlink.git
   cd heatlink
   ```

2. 启动服务:
   ```bash
   docker-compose up -d
   ```

3. 访问服务:
   - API: http://localhost:8000
   - API 文档: http://localhost:8000/api/docs
   - PgAdmin: http://localhost:5050 (邮箱: admin@heatlink.com, 密码: admin)
   - Redis Commander: http://localhost:8081
   - Flower 监控: http://localhost:5555

### 开发环境

如果您希望在本地运行后端服务以便更方便地调试，我们也提供了本地开发环境配置。

1. 使用本地开发环境启动脚本：
   ```bash
   ./local-dev.sh
   ```

   这将启动以下服务：
   - PostgreSQL 数据库
   - Redis 缓存
   - PgAdmin（PostgreSQL 管理界面）
   - Redis Commander（Redis 管理界面）

2. 在不同的终端窗口中运行以下命令：

   启动后端API服务：
   ```bash
   cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   启动Celery Worker：
   ```bash
   cd backend && python worker_start.py
   ```
   
   启动Flower监控：
   ```bash
   cd backend && celery -A worker.celery_app flower --port=5555
   ```

## 初始化数据

我们提供了一系列脚本来初始化系统所需的基础数据：

```bash
cd backend
python -m scripts.init_all
```

这将初始化：
- 新闻源配置
- 标签分类
- 管理员用户

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

## 许可证

本项目采用 MIT 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。 