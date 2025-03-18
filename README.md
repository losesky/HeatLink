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

## 后端服务启动脚本

项目提供了一个便捷的脚本 `start_server.py` 用于启动 HeatLink 后端服务。该脚本具有以下功能：

1. 自动同步数据库源和源适配器
2. 检测和处理数据库中的重复源记录
3. 缓存数据到Redis中
4. 启动API服务
5. 清理Chrome浏览器进程，防止端口占用问题

### 使用方法

#### 基本用法

最简单的启动方式：

```bash
python start_server.py
```

这将启动服务器，监听 `0.0.0.0:8000`，同步源适配器和数据库，并使用Redis缓存。

#### 命令行参数

脚本支持以下命令行参数：

- `--sync-only`: 只同步数据库和适配器，不启动服务
- `--no-cache`: 不使用Redis缓存
- `--host HOST`: 服务器监听地址，默认为0.0.0.0
- `--port PORT`: 服务器监听端口，默认为8000
- `--reload`: 启用热重载，开发环境下有用
- `--no-chromedriver`: 禁用Chrome驱动清理
- `--clean-ports`: 在启动前清理指定的端口

#### 使用示例

1. 在开发环境中运行（带热重载）
   ```bash
   python start_server.py --host 127.0.0.1 --port 8000 --reload
   ```

2. 仅同步数据库和源适配器，不启动服务
   ```bash
   python start_server.py --sync-only
   ```

3. 在生产环境中运行，指定端口
   ```bash
   python start_server.py --host 0.0.0.0 --port 80
   ```

4. 不使用Redis缓存（不推荐用于生产）
   ```bash
   python start_server.py --no-cache
   ```

5. 在启动前清理端口
   ```bash
   python start_server.py --clean-ports
   ```

### 开发者注意事项

#### 数据完整性处理

脚本包含以下数据完整性处理功能：

1. **重复源记录检测**：在同步过程开始前，脚本会检测数据库中是否存在相同ID的源记录
2. **自动清理重复记录**：当发现重复记录时，脚本会保留最新更新的记录，并删除其余重复记录
3. **事务处理**：所有删除和修复操作都在事务中执行，确保数据库一致性

#### 同步过程

脚本会检查数据库源和代码中的源适配器，进行以下操作：

1. 将代码中有但数据库中没有的源添加到数据库
2. 将数据库中有但代码中没有的源标记为非活跃（不会删除）
3. 修复属性不匹配的源（如名称、URL、类型等）

#### Redis缓存

如果启用Redis缓存，脚本会将以下内容缓存到Redis：

1. 所有源的基本信息（`sources:all`）
2. 源类型列表（`sources:types`）
3. 按类型分组的源列表（`sources:type:{type}`）
4. 每个源的详细信息（`sources:detail:{id}`）
5. 所有源的最新统计信息（`sources:stats`）

#### 优雅关闭

脚本注册了信号处理器，以便在收到SIGINT（Ctrl+C）或SIGTERM信号时优雅关闭，确保：

1. 所有挂起的数据库事务被正确提交
2. Redis连接被正确关闭
3. Selenium浏览器进程被正确终止
4. 临时端口被释放

#### 浏览器进程管理

脚本特别处理了Selenium WebDriver使用的Chrome浏览器进程：

1. 在启动时检测并清理遗留的Chrome进程
2. 监控并关闭使用了特定调试端口的Chrome实例
3. 在服务关闭时确保所有浏览器资源被正确释放

### 故障排除

#### 常见问题和解决方案

1. **Chrome进程未正确关闭**

   **症状**：服务退出后，端口（如33681、46143等）仍被占用。

   **解决方案**：
   - 使用 `--clean-ports` 参数在启动前清理端口
   - 手动终止遗留的Chrome进程：`ps aux | grep chrome | grep -v grep | awk '{print $2}' | xargs kill -9`
   - 确保在测试源时调用了适当的close()方法

2. **数据库连接错误**

   **症状**：日志中显示 "从数据库获取源记录失败" 错误。

   **解决方案**：
   - 确认 `.env` 文件中的 `DATABASE_URL` 配置正确
   - 检查 PostgreSQL 服务是否正在运行
   - 确认数据库用户具有访问权限

3. **Redis 连接错误**

   **症状**：日志中显示 "Redis缓存操作失败" 或 "连接到Redis失败" 错误。

   **解决方案**：
   - 确认 Redis 服务正在运行
   - 检查 `.env` 文件中的 `REDIS_URL` 配置是否正确
   - 如果 Redis 不可用，使用 `--no-cache` 参数禁用缓存功能

4. **服务启动错误**

   **症状**：服务无法启动，通常伴随着导入错误或模块未找到错误。

   **解决方案**：
   - 确认当前目录是项目根目录
   - 检查是否已安装所有依赖：`pip install -r backend/requirements.txt`
   - 验证 Python 路径设置正确

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