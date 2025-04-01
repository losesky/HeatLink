# 数据库错误修复指南

## 问题: 外键约束错误

当使用 `test_yicai.py` 或其他测试脚本保存数据到数据库时，可能会遇到以下错误:

```
psycopg2.errors.ForeignKeyViolation: insert or update on table "news" violates foreign key constraint "news_source_id_fkey"
DETAIL:  Key (source_id)=(yicai) is not present in table "sources".
```

这个错误表明尝试插入一条引用 `yicai` 作为 `source_id` 的新闻记录，但在 `sources` 表中不存在 ID 为 `yicai` 的记录。

## 解决方案

我们提供了两种解决方案:

### 1. 使用自动修复工具

直接运行修复脚本:

```bash
cd backend
python tests/fix_sources.py
```

这个脚本会:
- 检查数据库连接
- 检查 `sources` 表中是否存在 `yicai` 源
- 如果不存在，自动创建该记录
- 提供详细的日志和错误信息

### 2. 集成到测试流程

最新版本的 `run_yicai_test.sh` 已经集成了数据源检查功能，会在运行测试前自动检查并创建必要的数据源记录。

```bash
cd backend
bash tests/run_yicai_test.sh
```

这个脚本会:
- 检查环境设置
- 检查数据库连接
- 调用 `ensure_sources.py` 确保必要的数据源存在
- 然后再执行测试

### 手动解决 (如果自动方法失败)

如果自动方法失败，可以手动执行以下SQL来创建源记录:

```sql
INSERT INTO sources (
  id, name, description, url, type, status, country, language, 
  update_interval, cache_ttl, config, created_at, updated_at
) VALUES (
  'yicai', '第一财经', '第一财经新闻源', 'https://www.yicai.com/', 
  'web', 'active', 'CN', 'zh-CN', 
  '1800 seconds'::interval, '900 seconds'::interval, 
  '{"use_selenium": true, "headless": true}', 
  NOW(), NOW()
);
```

## 验证修复

要验证修复是否成功，请执行以下命令:

```bash
cd backend
python -c "from app.database import SessionLocal; from app.crud.source import get_source; db = SessionLocal(); source = get_source(db, 'yicai'); print(f'Source found: {source is not None}'); db.close()"
```

如果输出 `Source found: True`，则表示修复成功。

## 防止将来出现此问题

为防止将来出现此问题:

1. 始终使用最新版本的测试脚本，这些脚本已集成自动检查和修复功能
2. 在创建新的数据源适配器时，确保在测试前在数据库中创建相应的源记录
3. 考虑在项目初始化脚本中添加创建基本数据源的代码 