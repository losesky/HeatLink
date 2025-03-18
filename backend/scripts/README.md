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

# HeatLink 后端工具脚本

本目录包含一些用于HeatLink项目维护和管理的实用工具脚本。

## 可用工具

### 1. 新闻源适配器验证工具 (`validate_sources.py`)

这个工具用于检查数据库中的新闻源记录与代码中的适配器是否完全匹配，确保系统运行时不会因为不匹配导致问题。

#### 功能
- 检查代码中有适配器但数据库中没有对应记录的情况
- 检查数据库中有记录但代码中没有对应适配器的情况 
- 检查适配器和数据库记录的基本属性不匹配的情况(例如name, url等)
- 分析代码和数据库之间的差异，提供详细统计报告
- 导出验证结果到JSON文件，方便后续分析
- 清理数据库中无效或过时的记录
- 批处理模式支持，无需用户交互
- 自动检测需要额外参数的通用适配器
- 可选自动修复发现的问题

#### 使用方法
```bash
# 只检查不修复
python -m backend.scripts.validate_sources

# 自动修复发现的问题
python -m backend.scripts.validate_sources --fix

# 显示详细输出
python -m backend.scripts.validate_sources --verbose

# 显示详细输出并自动修复
python -m backend.scripts.validate_sources --fix --verbose

# 分析代码和数据库之间的差异
python -m backend.scripts.validate_sources --analyze

# 导出验证报告到文件
python -m backend.scripts.validate_sources --export report.json

# 清理无效的数据库记录
python -m backend.scripts.validate_sources --clean --fix

# 批处理模式（无需用户交互）
python -m backend.scripts.validate_sources --fix --batch

# 组合使用多个功能
python -m backend.scripts.validate_sources --analyze --export report.json --fix --clean --batch
```

#### 参数说明
- `--fix`: 自动修复发现的问题
- `--verbose`: 显示详细输出，包括调试信息
- `--analyze`: 分析代码和数据库之间的差异，提供统计报告
- `--export FILE`: 导出验证报告到指定的JSON文件
- `--clean`: 检测并清理数据库中无效或过时的记录
- `--batch`: 批处理模式，无需用户交互确认（自动回答"是"）

#### 修复功能
当使用`--fix`参数时，工具会：
- 为代码中有但数据库中没有的适配器创建对应的数据库记录
- 更新属性不匹配的数据库记录，使其与代码保持一致
- 当与`--clean`参数一起使用时，会删除数据库中无效的记录

#### 验证报告
导出的验证报告包含以下信息：
- 数据库源和代码适配器的基本信息
- 缺失数据库记录的源列表
- 缺失适配器的记录列表
- 属性不匹配的记录和具体不匹配的字段
- 需要额外参数的通用适配器列表

> **注意**：修复功能会修改数据库内容，请在使用前备份数据库。

## 如何添加新工具

1. 在本目录中创建新的Python脚本
2. 遵循现有工具的模式，确保提供清晰的文档和命令行参数
3. 更新此README以包含新工具的说明 