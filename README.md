# HeatLink - 多源新闻聚合系统

HeatLink是一个多源新闻聚合系统，可以从多个来源收集新闻和热点信息，并提供统一的访问接口。

## 功能特点

- 支持多种新闻源（API、网页、RSS）
- 自动定时抓取最新内容
- 内容分类与标签管理
- 用户收藏与阅读历史
- 用户订阅功能
- RESTful API接口
- 缓存机制提高性能

## 技术栈

- **后端**: FastAPI, SQLAlchemy, Alembic, Pydantic
- **数据库**: PostgreSQL
- **缓存**: Redis
- **任务队列**: Celery
- **容器化**: Docker, Docker Compose

## 快速开始

### 使用Docker Compose

1. 克隆仓库:
   ```bash
   git clone https://github.com/yourusername/heatlink.git
   cd heatlink
   ```

2. 启动服务:
   ```bash
   docker-compose up -d
   ```

3. 访问服务:
   - API: http://localhost:8000
   - API 文档: http://localhost:8000/api/docs
   - PgAdmin: http://localhost:5050 (邮箱: admin@heatlink.com, 密码: admin)
   - Redis Commander: http://localhost:8081

### 开发环境

如果您希望在本地运行后端服务以便更方便地调试，我们也提供了本地开发环境配置。

1. 使用本地开发环境启动脚本：
   ```bash
   ./local-dev.sh
   ```

   这将启动以下服务：
   - PostgreSQL 数据库
   - Redis 缓存
   - PgAdmin（PostgreSQL 管理界面）
   - Redis Commander（Redis 管理界面）

2. 在不同的终端窗口中运行以下命令：

   启动后端API服务：
   ```bash
   cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   启动Celery Worker：
   ```bash
   cd backend && python worker_start.py
   ```

## 初始化数据

我们提供了一系列脚本来初始化系统所需的基础数据：

```bash
cd backend
python -m scripts.init_all
```

这将初始化：
- 新闻源配置
- 标签分类
- 管理员用户

## API文档

启动服务后，可以通过以下地址访问API文档：
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## 项目结构

```
heatlink/
├── backend/                # 后端代码
│   ├── alembic/            # 数据库迁移
│   ├── app/                # 应用代码
│   │   ├── api/            # API路由
│   │   ├── core/           # 核心配置
│   │   ├── crud/           # 数据库操作
│   │   ├── db/             # 数据库连接
│   │   ├── models/         # 数据库模型
│   │   └── schemas/        # Pydantic模型
│   ├── scripts/            # 初始化脚本
│   └── worker/             # Celery任务
├── docker-compose.yml      # Docker Compose配置
├── docker-compose.dev.yml  # 开发环境Docker配置
└── local-dev.sh            # 本地开发环境启动脚本
```

## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

## 许可证

本项目采用 MIT 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。 