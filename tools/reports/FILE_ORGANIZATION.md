# HeatLink 项目文件组织指南

本文档提供了项目文件结构的概述，以及如何管理中间文件和临时文件的指导。

## 目录结构

```
HeatLink/
├── app/                      # 前端应用代码（如果有）
├── backend/                  # 后端API代码
│   ├── app/                  # 核心应用代码
│   ├── scripts/              # 数据初始化和管理脚本
│   ├── alembic/              # 数据库迁移文件
│   ├── DATA_MIGRATION.md     # 数据迁移指南
│   └── ...                   # 其他后端文件
├── db_backups/               # 数据库备份目录
├── logs/                     # 日志文件目录
├── tests/                    # 测试脚本和工具
├── docker/                   # Docker相关配置文件
├── archived/                 # 归档的旧脚本和文件
├── cleanup.sh                # 系统清理脚本
├── local-dev.sh              # 本地开发环境启动脚本
├── docker-compose.yml        # 生产环境Docker Compose配置
├── docker-compose.local.yml  # 本地开发环境Docker Compose配置
└── ...                       # 其他项目文件
```

## 重要文件类型

### 核心配置文件
- `.env.example` - 环境变量配置模板
- `.env.local` - 本地开发环境配置
- `.env` - 当前环境配置（由local-dev.sh从.env.local复制而来）
- `docker-compose*.yml` - Docker服务配置文件
- `Dockerfile*` - Docker镜像构建配置

### 脚本文件
- `local-dev.sh` - 本地开发环境启动脚本
- `cleanup.sh` - 系统清理脚本
- `health_check.sh` - 系统健康检查脚本
- `backend/scripts/*.py` - 数据管理和初始化脚本

### 数据文件
- `backend/scripts/init_*.py` - 初始化数据脚本
- `db_backups/*.sql` - 数据库备份文件

### 临时文件（可以安全删除）
- `__pycache__/` 目录 - Python编译缓存
- `*.pyc` - Python编译文件
- `celerybeat-schedule` - Celery调度数据文件
- `celery.pid` - Celery进程ID文件
- `backend/*.html` - 临时HTML文件
- `backend/*.json` - 临时JSON文件（除了配置文件）
- `.db_connection.json` - 临时数据库连接配置
- `.migration_status.txt` - 临时迁移状态文件
- `.data_status.json` - 临时数据状态文件

## 文件管理指南

### 日常开发时
1. 使用 `./local-dev.sh` 启动开发环境
2. 定期运行 `./cleanup.sh` 清理临时文件
3. 对于特定模块的开发测试，相关测试文件应放在 `tests/` 目录下

### 代码提交前
1. 运行 `./cleanup.sh` 清理临时文件和缓存
2. 确保所有配置文件不含敏感信息
3. 确认临时文件未被添加到Git索引

### 数据备份和恢复
参考 `backend/DATA_MIGRATION.md` 文件中的详细说明

## 中间文件分类和处理

### 可以安全删除的文件
1. **缓存文件**: `__pycache__` 目录和 `.pyc` 文件
2. **临时连接文件**: `.db_connection.json`, `.migration_status.txt`
3. **Celery相关文件**: `celerybeat-schedule`, `celery.pid`
4. **临时HTML/JSON文件**: `backend/*.html`, `backend/*.json`（注意保留配置JSON文件）

### 需要谨慎处理的文件
1. **日志文件**: 通常保留一段时间后再删除，如7天或30天
2. **数据库备份**: 根据备份策略定期清理过期备份
3. **环境配置文件**: 在修改前应先备份

### 归档策略
不再使用但可能还有参考价值的代码：
1. 移动到 `archived/` 目录
2. 添加简短说明文件（README.md），解释其功能和为何归档

## 使用清理脚本

项目提供了 `cleanup.sh` 脚本来帮助您清理临时文件：

```bash
# 运行清理脚本
./cleanup.sh
```

该脚本可以帮助您：
- 清理Python缓存文件
- 删除临时文件
- 整理测试文件
- 管理日志文件
- 检查过期备份

## 常见问题

### 磁盘空间不足
首先检查并清理以下内容：
1. 日志文件 - `logs/` 目录
2. 数据库备份 - `db_backups/` 目录
3. Docker镜像和容器 - 运行 `docker system prune`

### 重复的配置文件
保持配置文件的一致性：
1. 始终使用 `.env.local` 作为本地开发环境的主配置
2. 使用 `local-dev.sh` 来启动环境（它会自动复制 `.env.local` 到 `.env`）

### 性能问题
对于大型项目，及时清理缓存和临时文件可提高性能：
1. 定期运行 `./cleanup.sh`
2. 清理不必要的Docker镜像和容器
3. 优化大型日志文件 