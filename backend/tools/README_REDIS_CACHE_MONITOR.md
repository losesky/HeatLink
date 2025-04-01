# Redis 缓存监控工具

这个工具用于监控和管理 HeatLink 系统中的 Redis 缓存，特别是新闻源的缓存数据。它提供了多种功能，包括测试缓存集成、查看缓存统计信息、清理缓存、刷新特定新闻源的缓存等。

## 功能

1. **测试缓存集成**：验证新闻源数据是否正确写入 Redis 缓存
2. **查看缓存统计**：获取缓存使用情况的详细统计信息
3. **清理缓存**：删除特定模式的缓存键
4. **刷新缓存**：强制重新获取特定新闻源的数据并更新缓存
5. **列出缓存键**：列出所有匹配特定模式的缓存键
6. **导出缓存数据**：将缓存数据导出为 JSON 文件
7. **生成 HTML 报告**：创建包含缓存状态的详细 HTML 报告

## 使用方法

首先确保已设置 Redis URL 环境变量：

```bash
export REDIS_URL="redis://localhost:6379/0"
```

### 测试缓存集成

```bash
# 测试所有新闻源的缓存集成
python backend/tools/redis_cache_monitor.py test

# 测试特定新闻源
python backend/tools/redis_cache_monitor.py test --sources 36kr,ifeng

# 强制刷新缓存后测试
python backend/tools/redis_cache_monitor.py test --refresh
```

### 查看缓存统计

```bash
# 查看所有新闻源的缓存统计
python backend/tools/redis_cache_monitor.py stats

# 以JSON格式输出
python backend/tools/redis_cache_monitor.py stats --json

# 查看特定模式的缓存统计
python backend/tools/redis_cache_monitor.py stats --pattern "source:36kr*"
```

### 清理缓存

```bash
# 清理所有新闻源的缓存
python backend/tools/redis_cache_monitor.py clear

# 清理特定模式的缓存
python backend/tools/redis_cache_monitor.py clear --pattern "source:36kr"

# 强制清理，不需要确认
python backend/tools/redis_cache_monitor.py clear --force
```

### 刷新缓存

```bash
# 刷新特定新闻源的缓存
python backend/tools/redis_cache_monitor.py refresh --sources 36kr,ifeng
```

### 列出缓存键

```bash
# 列出所有新闻源的缓存键
python backend/tools/redis_cache_monitor.py list

# 列出特定模式的缓存键
python backend/tools/redis_cache_monitor.py list --pattern "source:36kr*"
```

### 导出缓存数据

```bash
# 导出所有新闻源的缓存数据
python backend/tools/redis_cache_monitor.py export --output ./cache_data

# 导出特定新闻源的缓存数据
python backend/tools/redis_cache_monitor.py export --output ./cache_data --sources 36kr,ifeng
```

### 生成 HTML 报告

```bash
# 生成包含缓存状态的 HTML 报告
python backend/tools/redis_cache_monitor.py report --output cache_report.html
```

## 报告内容

HTML 报告包含以下信息：

1. **缓存摘要**：
   - 总缓存键数
   - 总新闻条目数
   - 平均 TTL（生存时间）
   - 无缓存源数量

2. **缓存源详情**：
   - 源键名
   - TTL（生存时间）
   - 条目数量
   - 内存使用情况

3. **无缓存源列表**：列出所有没有缓存数据的新闻源

## 例子

1. 测试 36kr 新闻源的缓存集成并刷新：

   ```bash
   python backend/tools/redis_cache_monitor.py test --sources 36kr --refresh
   ```

2. 导出 36kr 和 ifeng 的缓存数据：

   ```bash
   python backend/tools/redis_cache_monitor.py export --output ./cache_exports --sources 36kr,ifeng
   ```

3. 生成 HTML 报告并在浏览器中查看：

   ```bash
   python backend/tools/redis_cache_monitor.py report --output cache_report.html
   # 然后用浏览器打开 cache_report.html
   ```

## 注意事项

1. 确保 Redis 服务器正在运行，并且 `REDIS_URL` 环境变量已正确设置
2. 清理缓存操作将永久删除缓存数据，请谨慎使用
3. 对于大型缓存，导出和生成报告可能需要较长时间 