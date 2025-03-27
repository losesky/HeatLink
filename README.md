# HeatLink - 多源新闻聚合系统

HeatLink是一个多源新闻聚合系统，可以从多个来源收集新闻和热点信息，并提供统一的访问接口。

## 系统架构

HeatLink采用现代化的微服务架构，主要由以下几个核心组件构成：

1. **API服务**：基于FastAPI构建的RESTful API，提供新闻数据的查询、管理和用户交互功能
2. **Worker服务**：负责后台任务处理，包括新闻抓取、数据处理和定时任务
3. **Beat服务**：Celery Beat调度器，负责定时触发任务
4. **数据库**：PostgreSQL关系型数据库，存储结构化数据
5. **缓存**：Redis缓存服务，提高系统性能并支持任务队列
6. **代理服务**：支持通过HTTP或SOCKS代理访问受限资源，提高数据获取可靠性

系统架构图：
```
┌─────────────┐     ┌─────────────┐      ┌─────────────┐
│   客户端    │────▶│  API服务    │◀───▶│  数据库     │
└─────────────┘     └──────┬──────┘      └─────────────┘
                          │                     ▲
                          ▼                     │
                    ┌─────────────┐      ┌─────────────┐
                    │  Redis缓存  │◀───▶│ Worker服务  │
                    └─────────────┘      └──────┬──────┘
                          ▲                     │
                          │                     ▼
                          │              ┌─────────────┐
                          └───────────── │  Beat服务   │
                                         └─────────────┘
                                                │
                                                ▼
                                         ┌─────────────┐
                                         │  代理服务   │
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

### 7. 源统计信息自动更新

系统实现了智能的源统计信息自动更新机制，用于监控和评估各新闻源的健康状态与性能：

- **自动包装**：通过`StatsUpdater`自动包装源适配器的`fetch`方法，无需修改现有代码
- **实时统计**：自动记录每次请求的成功率、响应时间和错误信息
- **累积更新**：聚合多次请求的统计数据，定期更新到数据库中
- **规范化处理**：自动处理源ID格式不一致问题（如下划线与连字符格式转换）
- **可配置更新间隔**：支持自定义统计信息的更新频率，平衡实时性与性能

### 8. 智能代理支持

系统新增了智能代理支持功能，解决某些数据源访问限制问题：

- **灵活的代理配置**：支持SOCKS5、HTTP和HTTPS多种代理协议
- **自动代理选择**：根据数据源特性自动选择合适的代理服务器
- **代理健康监控**：自动监控代理可用性并切换到可用代理
- **代理分组管理**：支持按地区、用途等对代理进行分组管理
- **自动故障转移**：代理失败时可配置自动尝试直连或切换备用代理
- **性能统计**：记录代理使用情况、成功率和响应时间等指标

代理管理的主要功能：
1. **自动识别需要代理的源**：系统会自动识别需要使用代理的数据源（如国际新闻、开发者社区等）
2. **智能调度**：根据代理的历史性能和当前负载分配代理资源
3. **实时监控**：监控代理健康状态，自动屏蔽异常代理
4. **API管理**：提供完整的REST API接口管理代理配置

统计更新器的工作流程：
1. 在调用源的`fetch`方法时，自动记录开始时间
2. 监控请求执行过程，捕获可能的异常
3. 计算请求耗时并更新内存中的统计缓存
4. 根据配置的更新间隔，定期将累积的统计信息写入数据库

这些统计信息可用于：
- 监控源的健康状态，及时发现异常
- 评估源的性能，优化资源分配
- 为自适应调度提供决策依据
- 生成源性能报告，指导系统优化

统计数据模型包含丰富的指标：
- **总请求数**：记录源被调用的总次数
- **成功率**：成功请求占总请求的比例
- **平均响应时间**：所有请求的平均耗时
- **错误次数**：失败请求的累计次数
- **最近错误**：最近一次错误的详细信息

通过这些统计信息，系统能够更智能地管理新闻源，提高数据获取的可靠性和效率。

## 系统要求

### 开发环境要求

- **Python**: 3.9+
- **PostgreSQL**: 12.0+
- **Redis**: 6.0+
- **Docker** (可选): 20.10+
- **Docker Compose** (可选): 2.0+

### 主要依赖

系统主要依赖以下Python库：

- **Web框架与API**：
  - FastAPI 0.103.0+：高性能异步API框架
  - Uvicorn 0.23.2+：ASGI服务器
  - Pydantic 2.4.2+：数据验证和设置管理

- **网络和通信**：
  - aiohttp 3.8.5+：异步HTTP客户端/服务器
  - httpx 0.25.0+：现代HTTP客户端
  - websockets 11.0.3+：WebSocket支持

- **代理支持**：
  - aiohttp-socks 0.8.1+：aiohttp的SOCKS代理支持
  - requests[socks] 2.31.0+：requests的SOCKS代理支持
  - PySocks 1.7.1+：SOCKS协议实现
  - python-socks 2.4.3+：纯Python SOCKS客户端库

- **数据库和ORM**：
  - SQLAlchemy 2.0.20+：Python SQL工具包和ORM
  - Alembic 1.12.0+：数据库迁移工具
  - psycopg2-binary 2.9.9+：PostgreSQL适配器
  - Redis 5.0.0+：Redis客户端

- **任务队列**：
  - Celery 5.3.4+：分布式任务队列
  - Flower 2.0.1+：Celery实时监控工具

- **数据处理**：
  - numpy 1.25.2+：科学计算库
  - pandas 2.1.0+：数据分析工具
  - scikit-learn 1.3.0+：机器学习库
  - jieba 0.42.1+：中文分词库

- **数据抓取**：
  - beautifulsoup4 4.12.2+：HTML/XML解析库
  - lxml 4.9.3+：高效XML和HTML处理库
  - Selenium 4.12.0+：自动化浏览器测试工具
  - feedparser 6.0.10+：RSS/Atom解析库

完整的依赖列表可在`requirements.txt`文件中查看。

## 数据模型设计

系统的核心数据模型包括：

1. **News**：新闻条目，包含标题、内容、来源、发布时间等信息
2. **Source**：新闻源，定义数据来源及其配置
3. **Category**：新闻分类
4. **Tag**：新闻标签
5. **User**：用户信息
6. **Subscription**：用户订阅关系
7. **ProxyConfig**：代理服务器配置

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
   - PUT /{id}/proxy：更新新闻源的代理设置

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

6. **/api/proxies**：代理管理
   - GET /：获取所有代理配置
   - POST /：创建新代理配置
   - GET /{proxy_id}：获取指定代理详情
   - PUT /{proxy_id}：更新代理配置
   - DELETE /{proxy_id}：删除代理配置
   - POST /test：测试代理连接
   - GET /stats：获取代理使用统计
   - PUT /domains：更新需要代理的域名列表

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

### 安装与依赖

1. 首先确保您已安装必要的依赖：
   - Python 3.9+
   - PostgreSQL 12.0+
   - Redis 6.0+

2. 克隆仓库:
   ```bash
   git clone https://github.com/losesky/heatlink.git
   cd heatlink
   ```

3. 安装Python依赖:
   ```bash
   pip install -r requirements.txt
   ```

4. 创建并配置环境变量文件:
   ```bash
   cp .env.example .env
   # 编辑 .env 文件设置您的数据库和Redis连接
   ```

### 使用Docker Compose

使用Docker Compose可以快速启动所有必要的服务：

1. 启动服务:
   ```bash
   docker-compose up -d
   ```

2. 访问服务:
   - API: http://localhost:8000
   - API 文档: http://localhost:8000/api/docs
   - PgAdmin: http://localhost:5050 (邮箱: admin@heatlink.com, 密码: admin)
   - Redis Commander: http://localhost:8081
   - Flower 监控: http://localhost:5555

### 使用启动脚本（非Docker环境）

我们提供了一系列脚本，使您能够轻松启动所有必要的服务：

1. 首先确保脚本具有执行权限：
   ```bash
   chmod +x *.sh
   ```

2. 依次启动服务：
   ```bash
   # 启动数据库和缓存服务
   ./local-dev.sh
   
   # 启动后端API服务（使用新的run_server.sh脚本）
   ./run_server.sh
   # 或使用旧的方式
   # python backend/start_server.py
   
   # 启动Celery任务系统
   ./run_celery.sh
   ```

3. 初始化系统配置（包括默认数据源、分类和代理配置）：
   ```bash
   cd backend
   python -m scripts.init_all  # 初始化基础数据
   python -m scripts.init_proxy  # 初始化代理配置
   ```

4. 停止服务：
   ```bash
   # 停止Celery服务
   ./stop_celery.sh
   
   # 停止API服务（如果使用run_server.sh启动）
   kill $(cat .server.pid)
   # 或使用进程查找
   pkill -f "python backend/start_server.py"
   
   # 停止基础设施服务
   docker-compose -f docker-compose.local.yml down
   ```

### 验证安装

安装完成后，您可以通过以下方式验证服务是否正常运行：

1. 检查API服务:
   ```bash
   curl http://localhost:8000/health
   ```

2. 检查代理配置（需要登陆验证）:
   ```bash
   curl http://localhost:8000/api/proxies
   ```

3. 检查新闻源（需要登陆验证）:
   ```bash
   curl http://localhost:8000/api/sources
   ```

4. 查看API文档：
   在浏览器中访问 http://localhost:8000/docs

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
   # 使用新的run_server.sh脚本（推荐）
   ./run_server.sh --reload
   
   # 或使用传统方式
   cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
   # 或使用start_server.py脚本（包含同步数据库功能）
   python backend/start_server.py --reload
   ```

   启动Celery任务系统：
   ```bash
   # 使用封装脚本启动Celery Worker和Beat
   ./run_celery.sh
   
   # 查看日志
   tail -f celery_worker.log
   tail -f celery_beat.log
   ```

   启动Flower监控：
   ```bash
   cd backend && celery -A worker.celery_app flower --port=5555
   ```

## 任务调度系统启动脚本

项目提供了专用的脚本来管理Celery任务调度系统，让您可以轻松启动和停止所有任务处理服务。

### run_celery.sh

`run_celery.sh` 脚本用于启动Celery的Worker和Beat进程，负责执行和调度所有后台任务。

#### 功能特点

- 自动检测已运行的Celery进程，避免重复启动
- 提供交互式选项，可选择终止已有进程并重新启动
- 自动激活虚拟环境(如果存在)
- 将日志输出到单独的文件(`celery_worker.log`和`celery_beat.log`)
- 记录进程PID到`celery.pid`文件，便于后续管理

#### 使用方法

```bash
chmod +x run_celery.sh  # 确保脚本有执行权限
./run_celery.sh
```

启动后，可以通过以下命令查看日志：
```bash
tail -f celery_worker.log  # 查看Worker日志
tail -f celery_beat.log    # 查看Beat日志
```

### stop_celery.sh

`stop_celery.sh` 脚本用于安全地停止所有Celery相关进程。

#### 功能特点

- 显示当前运行的Celery进程以便确认
- 先尝试优雅终止，然后在必要时强制终止顽固进程
- 自动清理`celery.pid`文件

#### 使用方法

```bash
chmod +x stop_celery.sh  # 确保脚本有执行权限
./stop_celery.sh
```

### 完整系统启动流程

要启动HeatLink的所有必要服务，请按照以下顺序操作：

1. **启动基础设施服务**
   ```bash
   ./local-dev.sh  # 开发环境
   # 或
   docker-compose up -d  # 生产环境
   ```

2. **启动后端API服务**
   ```bash
   # 使用便捷的Shell脚本（推荐）
   ./run_server.sh  # 生产环境
   ./run_server.sh --reload  # 开发环境，启用热重载
   
   # 或使用Python脚本
   python backend/start_server.py
   # 或(开发环境，启用热重载)
   python backend/start_server.py --reload
   ```

3. **启动Celery任务系统**
   ```bash
   ./run_celery.sh
   ```

4. **验证服务状态**
   ```bash
   # 使用健康检查脚本
   chmod +x health_check.sh
   ./health_check.sh
   
   # 或手动检查各个组件
   # 检查API服务
   curl http://localhost:8000/health
   curl http://localhost:8000/api/health  # 详细状态
   
   # 检查Celery进程
   ps aux | grep "[c]elery -A worker.celery_app" | grep -v grep
   
   # 查看日志
   tail -f logs/server_*.log  # 后端服务日志
   tail -f celery_worker.log
   tail -f celery_beat.log
   ```

5. **停止所有服务(完成后)**
   ```bash
   # 停止Celery
   ./stop_celery.sh
   
   # 停止API服务
   # 如果使用run_server.sh启动
   kill $(cat .server.pid)
   # 或使用进程查找
   pkill -f "python backend/start_server.py"
   
   # 停止基础设施服务
   docker-compose down  # 生产环境
   # 或
   docker-compose -f docker-compose.local.yml down  # 开发环境
   ```

### 任务调度系统监控

启动Celery后，您可以通过以下方式监控任务：

1. **查看任务日志**
   ```bash
   tail -f logs/celery_worker.log
   tail -f logs/celery_news_worker.log
   ```

2. **使用Flower监控界面**
   ```bash
   cd backend && celery -A worker.celery_app flower --port=5555
   ```
   然后访问 http://localhost:5555

3. **通过API查询任务状态**
   ```
   GET /api/tasks/status/{task_id}
   GET /api/tasks/active
   ```

### 任务调度系统故障排除

如果您在运行Celery任务时遇到问题，可以使用以下步骤进行故障排除：

1. **检查Celery进程是否正在运行**
   ```bash
   ps aux | grep celery
   ```

2. **运行综合修复脚本**
   ```bash
   python fix_celery_and_db.py
   ```
   此脚本会:
   - 修复数据库Schema问题
   - 修复stats_wrapper.py中的函数调用
   - 应用异步循环修复
   - 重启Celery服务
   - 测试Celery任务执行

3. **检查常见错误**
   - "Event loop is closed"错误: 这是由于在Celery任务中使用async/await代码引起的，可以通过应用asyncio_fix解决
   - "AttributeError: 'Source' object has no attribute 'news_count'"错误: 数据库Schema不匹配，运行数据库迁移
   - Redis连接问题: 确保Redis服务器正在运行，并且您的配置正确

4. **手动测试任务**
   ```bash
   python test_celery.py
   ```

5. **检查任务执行结果**
   ```bash
   python check_database.py
   ```

## 后端服务启动脚本

项目提供了两种启动后端服务的方式：通过 `run_server.sh` 便捷脚本或直接使用 `start_server.py`。

### run_server.sh 脚本

`run_server.sh` 是一个功能丰富的 Shell 脚本，封装了 `python backend/start_server.py` 命令，并增加了很多实用功能：

#### 功能特点

- **命令行参数支持**：支持所有 `start_server.py` 的原有参数
- **环境检查**：自动检测 Python 版本、查找并激活虚拟环境、验证核心依赖
- **配置检查**：检查 `.env` 文件是否存在，提供配置引导
- **进程管理**：检查服务是否已在运行，提供终止并重新启动的选项
- **日志管理**：自动创建带时间戳的日志文件，便于追踪
- **彩色输出**：用户友好的彩色命令行界面，增强可读性

#### 使用方法

```bash
# 确保脚本有执行权限
chmod +x run_server.sh

# 基本用法（默认在0.0.0.0:8000启动服务）
./run_server.sh

# 使用热重载（前台运行，适合开发）
./run_server.sh --reload

# 指定端口
./run_server.sh --port 8080

# 仅同步数据库，不启动服务
./run_server.sh --sync-only

# 获取帮助
./run_server.sh --help
```

#### 后台运行与查看日志

当不使用 `--reload` 参数时，服务默认会在后台运行：

```bash
# 查看实时日志
tail -f logs/server_YYYYmmdd_HHMMSS.log
```

#### 停止服务

```bash
# 使用PID文件终止进程
kill $(cat .server.pid)

# 或通过进程查找并终止
pkill -f "python backend/start_server.py"
```

### start_server.py 脚本

项目还提供了核心的 Python 启动脚本 `start_server.py`，可以直接使用：

#### 功能

1. 自动同步数据库源和源适配器
2. 检测和处理数据库中的重复源记录
3. 缓存数据到Redis中
4. 启动API服务
5. 清理Chrome浏览器进程，防止端口占用问题

#### 使用方法

##### 基本用法

最简单的启动方式：

```bash
python backend/start_server.py
```

这将启动服务器，监听 `0.0.0.0:8000`，同步源适配器和数据库，并使用Redis缓存。

##### 命令行参数

脚本支持以下命令行参数：

- `--sync-only`: 只同步数据库和适配器，不启动服务
- `--no-cache`: 不使用Redis缓存
- `--host HOST`: 服务器监听地址，默认为0.0.0.0
- `--port PORT`: 服务器监听端口，默认为8000
- `--reload`: 启用热重载，开发环境下有用
- `--no-chromedriver`: 禁用Chrome驱动清理
- `--clean-ports`: 在启动前清理指定的端口

##### 使用示例

1. 在开发环境中运行（带热重载）
   ```bash
   python backend/start_server.py --host 127.0.0.1 --port 8000 --reload
   ```

2. 仅同步数据库和源适配器，不启动服务
   ```bash
   python backend/start_server.py --sync-only
   ```

3. 在生产环境中运行，指定端口
   ```bash
   python backend/start_server.py --host 0.0.0.0 --port 80
   ```

4. 不使用Redis缓存（不推荐用于生产）
   ```bash
   python backend/start_server.py --no-cache
   ```

5. 在启动前清理端口
   ```bash
   python backend/start_server.py --clean-ports
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

## 代理服务配置

HeatLink 支持通过代理服务器访问受限制的数据源，特别是对于国际新闻源或需要特殊网络环境的数据源。代理功能完全集成到系统中，可以通过API或脚本进行管理。

### 初始化代理配置

系统提供了专门的初始化脚本来设置默认代理配置：

```bash
cd backend
python -m scripts.init_proxy
```

此脚本会执行以下操作：
1. 为需要代理的数据源（如GitHub、Bloomberg、BBC等）启用代理支持
2. 添加默认的本地SOCKS5代理配置（默认使用本地Xray/V2Ray SOCKS5代理端口）
3. 配置代理故障转移策略（默认配置代理失败时尝试直连）

### 代理配置项说明

代理配置包含以下主要参数：

- **协议(Protocol)**：支持SOCKS5、HTTP和HTTPS三种代理协议
- **主机(Host)**：代理服务器地址
- **端口(Port)**：代理服务器端口
- **用户名/密码**：用于需要认证的代理服务器
- **代理组(Group)**：按用途或地区对代理进行分组管理
- **优先级(Priority)**：决定代理选择顺序，数值越高优先级越高
- **健康检查URL**：用于验证代理连接的URL

### 使用本地代理

默认情况下，系统会使用配置为127.0.0.1:10606的本地SOCKS5代理。如果您使用其他代理软件或端口，可以通过以下方式修改：

1. **通过API修改**
   ```bash
   # 使用curl更新默认代理配置
   curl -X PUT "http://localhost:8000/api/proxies/1" \
     -H "Content-Type: application/json" \
     -d '{"host": "127.0.0.1", "port": 1080, "protocol": "SOCKS5"}'
   ```

2. **通过脚本添加新代理**
   ```python
   # 创建脚本add_proxy.py
   import asyncio
   from backend.worker.utils.proxy_manager import proxy_manager
   
   async def add_new_proxy():
       proxy_id = await proxy_manager.add_proxy({
           "name": "自定义代理",
           "protocol": "http",
           "host": "192.168.1.100",
           "port": 8080,
           "username": "user",  # 可选
           "password": "pass",  # 可选
           "priority": 10,
           "group": "custom"
       })
       print(f"添加了新代理，ID: {proxy_id}")
   
   if __name__ == "__main__":
       asyncio.run(add_new_proxy())
   ```

### 配置需要代理的数据源

您可以通过API或直接在数据库中配置哪些数据源需要使用代理：

```bash
# 为特定数据源启用代理
curl -X PUT "http://localhost:8000/api/sources/github/proxy" \
  -H "Content-Type: application/json" \
  -d '{"need_proxy": true, "proxy_fallback": true, "proxy_group": "default"}'
```

系统还支持设置全局代理域名列表，任何匹配这些域名的请求都会自动使用代理：

```bash
# 设置需要代理的域名列表
curl -X PUT "http://localhost:8000/api/proxies/domains" \
  -H "Content-Type: application/json" \
  -d '{"domains": ["github.com", "bbc.com", "bloomberg.com"]}'
```

### 代理健康监控

系统会自动监控代理健康状态并收集性能统计信息：

- 成功率和平均响应时间
- 历史请求总数和失败次数
- 最近错误信息和最后检查时间

这些信息可通过API查看：

```bash
# 获取代理统计信息
curl "http://localhost:8000/api/proxies/stats"
```

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

## 许可证

本项目采用 MIT 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。 