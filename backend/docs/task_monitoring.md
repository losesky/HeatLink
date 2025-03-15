# 监控 Celery 任务执行状态

本文档介绍如何监控 Celery 任务的执行状态和获取任务结果。

## 1. 使用命令行工具

我们提供了两个命令行工具来执行任务和查询任务状态：

### 执行任务

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

### 查询任务状态

使用 `task_status.py` 脚本查询任务状态：

```bash
# 查询任务状态
python task_status.py <task_id>

# 等待任务完成并获取结果
python task_status.py <task_id> --wait --timeout=30
```

## 2. 使用 Flower 监控工具

Flower 是 Celery 的实时监控工具，提供了一个 Web 界面来查看任务执行情况。

### 安装 Flower

```bash
pip install flower
```

### 启动 Flower

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

## 3. 使用 API 接口

我们提供了一组 API 接口来执行任务和查询任务状态：

### 执行任务

```
POST /api/tasks/run/high-frequency
POST /api/tasks/run/medium-frequency
POST /api/tasks/run/low-frequency
POST /api/tasks/run/all-news
POST /api/tasks/run/source-news/{source_id}
```

### 查询任务状态

```
GET /api/tasks/status/{task_id}
```

### 获取活跃任务列表

```
GET /api/tasks/active
```

## 4. 通过编程方式

你也可以在 Python 代码中直接使用 Celery 的 API 来执行任务和查询任务状态：

```python
from worker.celery_app import celery_app
from worker.tasks.news import fetch_source_news
from celery.result import AsyncResult

# 执行任务
result = fetch_source_news.delay('zhihu')
task_id = result.id

# 查询任务状态
task_result = AsyncResult(task_id, app=celery_app)
print(f"Task state: {task_result.state}")

# 等待任务完成并获取结果
result = task_result.get(timeout=10)
print(f"Task result: {result}")
```

## 5. 任务状态说明

Celery 任务状态包括：

- **PENDING**: 任务已创建，但尚未排队或执行
- **STARTED**: 任务已开始执行
- **SUCCESS**: 任务已成功完成
- **FAILURE**: 任务执行失败
- **RETRY**: 任务正在重试
- **REVOKED**: 任务已被撤销

## 6. 故障排除

如果你遇到任务监控问题，请检查：

1. Redis 服务是否正常运行
2. Celery worker 是否正常启动
3. 任务 ID 是否正确
4. 任务是否已过期（默认结果保留时间为 1 天）

如果需要更长时间保留任务结果，可以在 `celery_app.py` 中配置：

```python
celery_app.conf.result_expires = 60 * 60 * 24 * 7  # 7 天
``` 