# HeatLink 后端服务

HeatLink 后端服务是一个基于 FastAPI 和 Celery 构建的新闻聚合系统，支持从多个来源收集新闻和热点信息，并提供统一的访问接口。

## 目录结构

```
backend/
├── api/                # API 路由和端点
├── app/                # 应用核心代码
│   ├── core/           # 核心配置和工具
│   ├── crud/           # 数据库操作
│   ├── db/             # 数据库连接和模型
│   ├── models/         # 数据库模型
│   └── schemas/        # Pydantic 模型
├── docs/               # 文档
├── scripts/            # 脚本工具
├── tests/              # 测试代码
├── worker/             # Celery Worker 相关代码
│   ├── sources/        # 新闻源适配器
│   └── tasks/          # Celery 任务定义
├── main.py             # 主应用入口
├── worker_start.py     # Worker 启动脚本
├── worker_start_prod.py # 生产环境 Worker 启动脚本
├── task_status.py      # 任务状态查询工具
└── run_task.py         # 任务执行工具
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务

### 启动 API 服务

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 启动 Worker 服务

开发环境：
```bash
python worker_start.py
```

生产环境：
```bash
python worker_start_prod.py
```

## 任务监控与管理

HeatLink 使用 Celery 作为任务队列系统，提供了多种方式来监控和管理任务执行状态。

### 1. 命令行工具

我们提供了两个命令行工具来执行任务和查询任务状态：

#### 执行任务

使用 `run_task.py` 脚本执行任务：

```bash
# 执行高频更新任务
python run_task.py high_freq

# 执行指定新闻源更新任务
python run_task.py source_news --source-id=zhihu

# 执行清理任务，指定天数
python run_task.py cleanup --days=30

# 执行任务并等待结果
python run_task.py high_freq --wait --timeout=60
```

可用的任务类型：
- `high_freq`: 高频更新任务（10分钟一次）
- `medium_freq`: 中频更新任务（30分钟一次）
- `low_freq`: 低频更新任务（1小时一次）
- `all_news`: 更新所有新闻源
- `source_news`: 更新指定新闻源（需要 `--source-id` 参数）
- `cleanup`: 清理旧数据（可选 `--days` 参数）
- `analyze`: 分析新闻趋势（可选 `--days` 参数）

#### 查询任务状态

使用 `task_status.py` 脚本查询任务状态：

```bash
# 查询任务状态
python task_status.py <task_id>

# 等待任务完成并获取结果
python task_status.py <task_id> --wait --timeout=30
```

### 2. Flower 监控工具

Flower 是 Celery 的实时监控工具，提供了一个 Web 界面来查看任务执行情况。

#### 安装 Flower

```bash
pip install flower
```

#### 启动 Flower

```bash
celery -A worker.celery_app flower --port=5555
```

然后你可以在浏览器中访问 `http://localhost:5555` 来查看：

- 活跃任务列表
- 已完成任务列表
- 任务执行时间统计
- Worker 状态
- 任务结果
- 任务详情

### 3. API 接口

我们提供了一组 API 接口来执行任务和查询任务状态：

#### 执行任务

```
POST /api/tasks/run/high-frequency
POST /api/tasks/run/medium-frequency
POST /api/tasks/run/low-frequency
POST /api/tasks/run/all-news
POST /api/tasks/run/source-news/{source_id}
```

#### 查询任务状态

```
GET /api/tasks/status/{task_id}
```

#### 获取活跃任务列表

```
GET /api/tasks/active
```

### 4. 任务状态说明

Celery 任务状态包括：

- **PENDING**: 任务已创建，但尚未排队或执行
- **STARTED**: 任务已开始执行
- **SUCCESS**: 任务已成功完成
- **FAILURE**: 任务执行失败
- **RETRY**: 任务正在重试
- **REVOKED**: 任务已被撤销

### 5. 故障排除

如果你遇到任务监控问题，请检查：

1. Redis 服务是否正常运行
2. Celery worker 是否正常启动
3. 任务 ID 是否正确
4. 任务是否已过期（默认结果保留时间为 1 天）

## 源统计信息监控

HeatLink 实现了一个自动化的源统计信息监控系统，用于跟踪和分析各新闻源的性能和可靠性。

### 1. 统计更新器 (StatsUpdater)

统计更新器是一个轻量级的包装器，自动跟踪新闻源调用的成功率、响应时间和错误信息。其主要特点包括：

- **透明集成**：自动包装源适配器的 `fetch` 方法，无需修改现有源代码
- **优化的数据库操作**：使用内存缓存聚合统计数据，按配置间隔批量更新数据库
- **源ID规范化**：自动处理源ID格式不一致问题，确保数据库记录一致性
- **详细日志**：提供全面的日志记录，便于调试和监控

```python
# 统计更新器全局配置示例
from worker.stats_wrapper import stats_updater

# 启用统计更新
stats_updater.enabled = True

# 设置数据库更新间隔（秒）
stats_updater.update_interval = 300  # 5分钟
```

### 2. 使用源管理器触发统计更新

统计更新器与 `NewsSourceManager` 紧密集成，当通过源管理器调用源的 `fetch` 方法时，会自动触发统计更新：

```python
# 通过源管理器获取新闻，会自动更新统计信息
from worker.sources.manager import source_manager

# 获取指定源的新闻
news_items = await source_manager.fetch_news('thepaper-selenium')
```

### 3. 统计数据模型

系统使用 `SourceStats` 数据库模型存储统计信息，包含以下关键指标：

- `source_id`: 新闻源标识符
- `success_rate`: 成功率（0-1范围内的浮点数）
- `avg_response_time`: 平均响应时间（毫秒）
- `total_requests`: 总请求次数
- `error_count`: 错误次数
- `last_error`: 最近一次错误信息
- `created_at`: 记录创建时间
- `updated_at`: 记录更新时间

### 4. 查询统计数据

可以通过以下方式查询统计数据：

```python
# 获取指定源的最新统计数据
from app.db.session import SessionLocal
from app.models.source_stats import SourceStats

db = SessionLocal()
latest_stats = db.query(SourceStats).filter(
    SourceStats.source_id == 'thepaper-selenium'
).order_by(SourceStats.created_at.desc()).first()
db.close()

print(f"成功率: {latest_stats.success_rate}")
print(f"平均响应时间: {latest_stats.avg_response_time}ms")
print(f"总请求数: {latest_stats.total_requests}")
```

### 5. API 访问

系统会通过API提供源统计数据，可用于监控仪表板和性能分析：

```
GET /api/sources/stats
GET /api/sources/stats/{source_id}
```

### 6. 故障排除

如果统计更新不起作用：

1. 确认 `stats_updater.enabled` 设置为 `True`
2. 检查是否通过 `NewsSourceManager.fetch_news()` 方法调用源（直接调用源的 `fetch` 方法不会触发统计更新）
3. 验证源ID在代码和数据库中的格式是否一致（统计更新器会尝试将下划线转换为连字符）
4. 查看日志中是否有与 `StatsUpdater` 相关的错误信息

## API 文档

启动服务后，可以通过以下地址访问 API 文档：

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## 环境变量

可以通过 `.env` 文件或环境变量配置以下参数：

- `DATABASE_URL`: 数据库连接 URL
- `REDIS_URL`: Redis 连接 URL
- `SECRET_KEY`: JWT 密钥
- `CELERY_BROKER_URL`: Celery 消息代理 URL
- `CELERY_RESULT_BACKEND`: Celery 结果后端 URL
- `CELERY_CONCURRENCY`: Celery worker 并发数
- `CELERY_USER_ID`: Celery worker 用户 ID（非 root 用户）
- `CELERY_GROUP_ID`: Celery worker 组 ID（非 root 组）
- `IGNORE_ROOT_WARNING`: 是否忽略 root 用户警告（开发环境）

## 更多文档

详细文档请参考 `docs/` 目录：

- [任务监控](docs/task_monitoring.md): 详细的任务监控指南
- [Worker 警告处理](docs/worker_warnings.md): 处理 Celery worker 警告的方法

# 财联社数据源维护指南

本文档提供财联社（CLS）数据源的维护指南，包括常见问题、解决方案和测试方法。

## 数据源概述

财联社（CLS）是一个财经新闻和数据提供商，我们通过以下途径获取数据：

1. 网页抓取（首选方式）
   - 电报页面：`https://www.cls.cn/telegraph`
   - 文章页面：`https://www.cls.cn/detail`

2. 备用API（当网页抓取失败时使用）
   - 电报API：获取最新电报内容
   - 文章API：获取最新文章列表

## 常见问题与解决方案

### 1. 网站结构变化导致抓取失败

**症状**: 数据源状态变为`ERROR`，日志中显示找不到特定的HTML元素或类名。

**解决方案**:
- 检查网站是否已更新结构
- 更新抓取逻辑以适应新的网站结构
- 如果网站结构频繁变化，考虑增强正则表达式提取方法

### 2. 移动版与桌面版网站结构不同

**症状**: 使用不同的用户代理获取到不同的HTML结构，导致抓取失败。

**解决方案**:
- 确保使用桌面版用户代理
- 实现同时支持移动版和桌面版的抓取逻辑
- 使用更通用的提取方法，如正则表达式

### 3. API访问限制或变更

**症状**: API返回错误状态码或无效数据。

**解决方案**:
- 检查API端点是否变更
- 确认是否受到了访问频率限制
- 优先使用网页抓取方法作为备选

## 维护工具

### 1. 健康检查脚本

使用`check_sources_health.py`脚本检查数据源状态并自动修复：

```bash
cd backend
python check_sources_health.py
```

### 2. 定期健康检查

将`run_sources_health_check.sh`脚本添加到crontab，定期执行健康检查：

```bash
# 每4小时执行一次健康检查
0 */4 * * * /path/to/backend/run_sources_health_check.sh
```

### 3. 手动测试脚本

使用`test_cls_telegraph.py`脚本测试电报页面抓取功能：

```bash
python test_cls_telegraph.py
```

## 数据库配置

财联社相关的数据源在数据库中的配置如下：

- `cls`: 财联社电报和文章主源
  - 配置：`use_scraping=True, use_backup_api=True`
  - 类型：`WEB`
  - 状态：`ACTIVE`

- `cls-article`: 财联社文章专用源
  - 配置：`use_scraping=True, use_backup_api=True`
  - 类型：`WEB`
  - 状态：`ACTIVE`

## 故障排除流程

当数据源处于`ERROR`状态时，按照以下步骤排除故障：

1. 检查日志文件，确定错误原因
2. 运行测试脚本验证数据源的各个组件
3. 更新抓取逻辑（如有必要）
4. 重置数据源状态为`ACTIVE`
5. 监控数据源，确保恢复正常

## 更新历史

- 2025-03-23: 更新电报页面抓取逻辑，增加对移动版网站的支持
- 2025-03-23: 添加正则表达式提取作为备用方法
- 2025-03-23: 创建健康检查和维护脚本 