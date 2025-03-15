# 数据库初始化脚本

本目录包含用于初始化HeatLink系统数据库的脚本。

## 脚本说明

- `init_all.py`: 主初始化脚本，运行所有初始化脚本
- `init_sources.py`: 初始化新闻源数据
- `init_tags.py`: 初始化标签数据
- `create_admin.py`: 创建管理员用户

## 使用方法

### 初始化所有数据

运行以下命令初始化所有数据（包括新闻源、标签和管理员用户）：

```bash
cd backend
python scripts/init_all.py
```

### 仅初始化新闻源

```bash
cd backend
python scripts/init_sources.py
```

### 仅初始化标签

```bash
cd backend
python scripts/init_tags.py
```

### 仅创建管理员用户

```bash
cd backend
python scripts/create_admin.py
```

## 注意事项

1. 运行脚本前，请确保已经完成数据库迁移：

```bash
cd backend
alembic upgrade head
```

2. 脚本会检查数据是否已存在，不会重复添加相同的数据。

3. 创建管理员用户时，密码长度必须不少于8个字符。

4. 所有脚本都会自动加载项目根目录下的 `.env` 文件中的环境变量。 