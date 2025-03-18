# HeatLink 后端服务启动脚本

本文档说明如何使用 `start_server.py` 脚本启动 HeatLink 后端服务。该脚本具有以下功能：

1. 自动同步数据库源和源适配器
2. 缓存数据到Redis中
3. 启动API服务

## 前提条件

在使用此脚本前，请确保：

1. PostgreSQL 数据库已配置并运行
2. Redis 服务器已启动（除非使用 `--no-cache` 参数）
3. 已安装所有必要的依赖项 (`pip install -r requirements.txt`)
4. `.env` 文件中已配置必要的环境变量

## 使用方法

### 基本用法

最简单的启动方式：

```bash
cd backend
python start_server.py
```

这将启动服务器，监听 `0.0.0.0:8000`，同步源适配器和数据库，并使用Redis缓存。

### 命令行参数

脚本支持以下命令行参数：

- `--sync-only`: 只同步数据库和适配器，不启动服务
- `--no-cache`: 不使用Redis缓存
- `--host HOST`: 服务器监听地址，默认为0.0.0.0
- `--port PORT`: 服务器监听端口，默认为8000
- `--reload`: 启用热重载，开发环境下有用

### 使用示例

#### 1. 在开发环境中运行（带热重载）

```bash
python start_server.py --host 127.0.0.1 --port 8000 --reload
```

#### 2. 仅同步数据库和源适配器，不启动服务

```bash
python start_server.py --sync-only
```

#### 3. 在生产环境中运行，指定端口

```bash
python start_server.py --host 0.0.0.0 --port 80
```

#### 4. 不使用Redis缓存（不推荐用于生产）

```bash
python start_server.py --no-cache
```

## 开发者注意事项

### 同步过程

脚本首先会检查数据库源和代码中的源适配器，进行以下操作：

1. 将代码中有但数据库中没有的源添加到数据库
2. 将数据库中有但代码中没有的源标记为非活跃（不会删除）
3. 修复属性不匹配的源（如名称、URL、类型等）

### Redis缓存

如果启用Redis缓存，脚本会将以下内容缓存到Redis：

1. 所有源的基本信息（`sources:all`）
2. 源类型列表（`sources:types`）
3. 按类型分组的源列表（`sources:type:{type}`）
4. 每个源的详细信息（`sources:detail:{id}`）
5. 所有源的最新统计信息（`sources:stats`）

这样，外部接口可以通过缓存数据获取信息，而无需每次都查询数据库，提高性能和响应速度。

### 日志记录

脚本使用Python标准日志模块，记录所有操作和错误信息。日志格式为：
```
timestamp - logger_name - level - message
```

### 优雅关闭

脚本注册了信号处理器，以便在收到SIGINT（Ctrl+C）或SIGTERM信号时优雅关闭，确保：

1. 所有挂起的数据库事务被正确提交
2. Redis连接被正确关闭
3. 其他资源被正确释放 