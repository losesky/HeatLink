# 处理 Celery Worker 警告

本文档解释如何处理运行 Celery worker 时可能出现的警告。

## 1. broker_connection_retry 配置警告

**警告信息:**
```
CPendingDeprecationWarning: The broker_connection_retry configuration setting will no longer determine
whether broker connection retries are made during startup in Celery 6.0 and above.
If you wish to retain the existing behavior for retrying connections on startup,
you should set broker_connection_retry_on_startup to True.
```

**解决方案:**
我们已经在 `worker/celery_app.py` 中添加了 `broker_connection_retry_on_startup=True` 配置，这将解决此警告。

## 2. 以超级用户权限运行 worker 的安全警告

**警告信息:**
```
SecurityWarning: You're running the worker with superuser privileges: this is
absolutely not recommended!

Please specify a different user using the --uid option.

User information: uid=0 euid=0 gid=0 egid=0
```

**解决方案:**
在生产环境中，应该使用非 root 用户运行 Celery worker。我们提供了几种方法来解决这个问题：

### 方法 1: 使用环境变量

设置以下环境变量来指定用户 ID：

```bash
export CELERY_USER_ID=1000  # 替换为实际的非 root 用户 ID
```

然后运行 worker：

```bash
python worker_start.py
```

如果你想忽略 root 用户警告（不推荐在生产环境中这样做），可以设置：

```bash
export IGNORE_ROOT_WARNING=true
python worker_start.py
```

### 方法 2: 使用生产环境启动脚本

我们提供了一个专门的生产环境启动脚本 `worker_start_prod.py`，它将强制使用非 root 用户：

```bash
python worker_start_prod.py
```

你可以通过环境变量自定义用户 ID 和组 ID：

```bash
export CELERY_USER_ID=1000  # 替换为实际的非 root 用户 ID
export CELERY_GROUP_ID=1000  # 替换为实际的非 root 组 ID
python worker_start_prod.py
```

### 方法 3: 直接使用 Celery 命令

你也可以直接使用 Celery 命令，并指定 `--uid` 参数：

```bash
celery -A worker.celery_app worker --loglevel=info --concurrency=4 --queues=main-queue --uid=1000 --gid=1000
```

## 注意事项

- 在开发环境中，可以通过设置 `IGNORE_ROOT_WARNING=true` 来忽略超级用户警告，但在生产环境中应该解决它。
- 确保指定的用户和组有足够的权限访问应用程序所需的文件和目录。
- 如果你在容器中运行应用程序，可能需要调整容器配置以支持非 root 用户。 