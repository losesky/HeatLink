# HeatLink 维护工具集

此目录包含HeatLink项目的各种维护工具和脚本，用于系统监控、诊断和修复。

## 目录结构

- `data_sources/`: 数据源监控和修复工具
- `database/`: 数据库维护和修复工具
- `system/`: 系统维护和健康检查工具
- `celery/`: Celery任务和进程管理工具
- `cleanup/`: 项目清理和整理工具
- `diagnostics/`: 系统诊断工具
- `reports/`: 项目文档和报告
- `deprecated/`: 已弃用但保留作参考的工具

## 使用指南

### 数据源工具

```bash
# 检查数据源健康状态
python tools/data_sources/check_sources_health.py

# 验证特定数据源修复
python tools/data_sources/verify_thepaper_fix.py
```

### 数据库工具

```bash
# 修复数据库
chmod +x tools/database/fix_database.sh
./tools/database/fix_database.sh

# 验证数据完整性
python tools/database/verify_data.py verify
```

### 系统工具

```bash
# 健康检查
chmod +x tools/system/health_check.sh
./tools/system/health_check.sh
```

### Celery工具

```bash
# 启动Celery服务
chmod +x tools/celery/run_celery.sh
./tools/celery/run_celery.sh

# 停止Celery服务
chmod +x tools/celery/stop_celery.sh
./tools/celery/stop_celery.sh

# 监控任务
python tools/celery/monitor_tasks.py
```

### 清理工具

```bash
# 清理项目临时文件
chmod +x tools/cleanup/cleanup.sh
./tools/cleanup/cleanup.sh
```

## 文档

完整的项目文档请参阅 `reports/` 目录下的文件。
