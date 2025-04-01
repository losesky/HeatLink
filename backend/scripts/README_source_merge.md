# 新闻源合并

本次更新合并了系统中的重复新闻源，以减少冗余并提高系统性能。

## 合并的新闻源

1. **财联社相关新闻源**:
   - 保留: `cls` (财联社)
   - 合并: `cls-article` (财联社文章)
   - 理由: 两个新闻源返回相似内容，可以通过一个统一的新闻源提供

2. **彭博社相关新闻源**:
   - 保留: `bloomberg` (彭博社)
   - 合并: `bloomberg-china` (彭博社中国)
   - 理由: 两个新闻源返回相似内容，可以通过一个统一的新闻源进行配置

## 实现细节

1. 创建了 `merge_duplicate_sources.py` 脚本用于:
   - 合并数据库中的新闻条目，避免数据丢失
   - 处理可能的ID冲突
   - 清理多余的新闻源记录

2. 更新了代码实现:
   - 修改 `CLSNewsSource` 类，增加了文章支持功能 
   - 修改 `BloombergNewsSource` 类，增加了中国新闻支持功能
   - 移除了冗余的 `CLSArticleNewsSource` 和 `BloombergChinaNewsSource` 类
   - 更新了 `sources/__init__.py` 中的导出列表
   - 更新了 `factory.py` 中的工厂方法

3. 更新了初始化脚本:
   - 从 `init_sources.py` 中移除重复的新闻源配置

## 如何使用

1. 运行数据库迁移:
   ```bash
   python backend/scripts/merge_duplicate_sources.py
   ```

2. 重启服务以应用代码变更:
   ```bash
   ./run_server.sh restart
   ```

## 变更排查

如果遇到问题，可以:

1. 检查日志 (`logs/app.log`) 以确认是否有错误
2. 使用API验证合并的新闻源是否正常工作:
   - `/api/v1/news/sources/cls` - 应返回财联社的所有新闻（包括原cls-article内容）
   - `/api/v1/news/sources/bloomberg` - 应返回彭博社的所有新闻（包括原bloomberg-china内容） 