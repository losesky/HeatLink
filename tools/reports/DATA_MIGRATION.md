# 数据迁移与重部署指南

本文档提供了在不同环境间迁移数据，以及在重新部署系统时避免数据问题的详细指引。

## 数据备份与恢复

### 自动备份

`local-dev.sh` 脚本在每次启动时会自动检查现有数据库并创建备份，备份文件保存在项目根目录的 `db_backups` 文件夹中。这个备份对于防止开发过程中的数据丢失很有用。

### 手动备份

可以使用以下命令手动创建数据库备份：

```bash
# 对正在运行的数据库进行备份
docker exec -t heatlink-postgres-local pg_dump -U postgres -d heatlink_dev > backup_$(date +%Y%m%d_%H%M%S).sql

# 或使用我们提供的数据导出脚本 (仅备份核心数据)
cd backend
python scripts/verify_data.py export --output ../data_export.json
```

### 数据恢复

从 SQL 备份恢复：

```bash
# 首先确保数据库容器在运行
docker compose -f docker-compose.local.yml up -d

# 从 SQL 文件恢复
cat backup.sql | docker exec -i heatlink-postgres-local psql -U postgres -d heatlink_dev

# 重启服务
docker compose -f docker-compose.local.yml restart
```

从导出的 JSON 数据恢复：

```bash
cd backend
python scripts/verify_data.py import --input ../data_export.json
```

## 数据验证与修复

我们提供了一个专用的数据验证脚本，可以检查数据一致性问题并自动修复一些常见问题：

```bash
# 验证数据
cd backend
python scripts/verify_data.py verify

# 显示详细信息
python scripts/verify_data.py verify --verbose

# 尝试自动修复问题
python scripts/verify_data.py verify --fix
```

## 跨环境迁移数据

当需要在开发环境、测试环境和生产环境之间迁移数据时，推荐以下流程：

1. **导出源环境数据**：
   ```bash
   cd backend
   python scripts/verify_data.py export --output data_export.json
   ```

2. **将导出的 JSON 文件复制到目标环境**

3. **在目标环境中导入数据**：
   ```bash
   cd backend
   python scripts/verify_data.py import --input data_export.json
   ```

   如果需要清除目标环境中的现有数据：
   ```bash
   python scripts/verify_data.py import --input data_export.json --clear
   ```

## 重新部署系统的最佳实践

在重新部署系统时，遵循以下步骤可以最大程度地保护数据一致性：

1. **部署前备份**：
   ```bash
   # 如果有运行中的数据库
   docker exec -t heatlink-postgres-local pg_dump -U postgres -d heatlink_dev > pre_deploy_backup.sql
   
   # 或使用核心数据导出
   cd backend
   python scripts/verify_data.py export --output pre_deploy_data.json
   ```

2. **清理部署**：
   ```bash
   ./local-dev.sh
   ```
   该脚本会自动：
   - 创建数据备份
   - 启动服务
   - 执行数据库迁移
   - 验证数据一致性
   - 必要时初始化基础数据

3. **部署后验证**：
   ```bash
   cd backend
   python scripts/verify_data.py verify --verbose
   ```

4. **如有问题，从备份恢复**：
   ```bash
   cat pre_deploy_backup.sql | docker exec -i heatlink-postgres-local psql -U postgres -d heatlink_dev
   ```

## 常见问题与解决方案

### 数据库迁移失败

如果迁移失败，可以尝试：

1. 检查日志确定失败原因
2. 使用 `alembic stamp head` 标记当前版本
3. 创建新的迁移：`alembic revision --autogenerate -m "Fix migration"`
4. 应用新迁移：`alembic upgrade head`

### 缺少基础数据

如果 `sources`、`categories` 或 `tags` 表为空：

```bash
cd backend
python scripts/init_all.py
```

或者手动初始化各个组件：

```bash
cd backend
python scripts/init_sources.py
python scripts/init_tags.py
python scripts/create_admin.py --non-interactive
```

### 数据关联不一致

使用验证工具修复数据关联：

```bash
cd backend
python scripts/verify_data.py verify --fix
```

## 管理员账户

在重新部署时，可能需要创建新的管理员账户：

```bash
# 交互式创建
cd backend
python scripts/create_admin.py

# 或非交互式创建 (自动生成密码)
python scripts/create_admin.py --non-interactive --email admin@example.com

# 指定密码
python scripts/create_admin.py --non-interactive --email admin@example.com --password secure_password
```

## 完全重置环境

如果需要完全重置开发环境：

```bash
# 停止所有容器并删除卷
docker compose -f docker-compose.local.yml down -v

# 重新启动环境
./local-dev.sh
```

这会删除所有数据并重新初始化环境。 