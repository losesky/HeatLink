# HeatLink 维护工具集

此目录包含HeatLink项目的各种维护工具和脚本，用于系统监控、诊断、数据管理和服务维护。

## 目录结构

- `data_sources/`: 数据源监控和修复工具
- `database/`: 数据库维护、验证和用户管理工具
- `system/`: 系统维护和健康检查工具
- `celery/`: Celery任务和进程管理工具
- `reports/`: 项目文档和报告
- `diagnostics/`: 系统诊断工具
- `deprecated/`: 已弃用但保留作参考的工具

## 使用指南

### 数据源工具

数据源工具用于监控、管理和修复各种数据源的连接和数据获取问题。

```bash
# 检查所有数据源的健康状态
python tools/data_sources/check_sources_health.py

# 修复特定数据源 (以 thepaper 为例)
python tools/data_sources/fix_thepaper_source.py

# 验证特定数据源修复是否成功
python tools/data_sources/verify_thepaper_fix.py
```

### 数据库工具

数据库工具用于维护数据库结构、验证数据完整性、创建管理员账户等操作。

```bash
# 修复数据库常见问题
chmod +x tools/database/fix_database.sh
./tools/database/fix_database.sh

# 验证数据完整性
python tools/database/verify_data.py verify

# 创建管理员账户
python tools/database/create_admin.py --username admin --password secure_password --email admin@example.com

# 修复分类数据
python tools/database/fix_categories.py
```

### 系统工具

系统工具用于检查系统健康状态、管理本地开发环境等。

```bash
# 健康检查（检查 API、数据库、Redis、Celery 等服务的状态）
chmod +x tools/system/health_check.sh
./tools/system/health_check.sh

# 自定义 API 端点进行健康检查
API_HOST=example.com API_PORT=9000 ./tools/system/health_check.sh

# 本地开发环境管理
chmod +x tools/system/local-dev.sh
./tools/system/local-dev.sh
```

### Celery工具

Celery工具用于管理和监控异步任务处理系统。

```bash
# 启动Celery服务
chmod +x tools/celery/run_celery.sh
./tools/celery/run_celery.sh

# 停止Celery服务
chmod +x tools/celery/stop_celery.sh
./tools/celery/stop_celery.sh

# 监控任务执行状态和性能
python tools/celery/monitor_tasks.py

# 手动执行特定任务
python tools/celery/run_task.py --task task_name --args '{"arg1": "value1"}'
```

## 文档与报告

`reports/` 目录包含项目相关的文档和报告：

- `DATA_MIGRATION.md`: 数据迁移流程和最佳实践
- `FILE_ORGANIZATION.md`: 文件组织结构说明
- `MAINTENANCE_SCRIPTS_REPORT.md`: 维护脚本的使用报告和性能分析

## 健康检查详解

`health_check.sh` 脚本是一个全面的系统健康检查工具，它可以：

1. 检测运行环境（主机系统或Docker容器）
2. 显示操作系统和内核信息
3. 检查API服务状态及详细健康状况
4. 检查数据库和Redis服务状态
5. 监控Celery Worker和Beat进程
6. 检查系统资源（CPU、内存、磁盘空间）
7. 显示网络连接状态和关键端口

该脚本支持通过环境变量自定义API检查的主机和端口：

```bash
# 使用默认配置 (localhost:8000)
./tools/system/health_check.sh

# 使用自定义API端点
API_HOST=api.example.com API_PORT=8080 ./tools/system/health_check.sh
```

## 贡献指南

如需添加新工具或改进现有工具，请遵循以下原则：

1. 保持脚本的独立性和可重用性
2. 提供详细的使用说明和文档
3. 确保脚本有适当的错误处理和日志记录
4. 对于关键维护操作，添加确认步骤以防止意外执行
