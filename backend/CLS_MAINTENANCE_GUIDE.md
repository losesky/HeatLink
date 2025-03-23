# 财联社数据源维护指南

本文档提供了财联社（CLS）数据源的维护指南，包括常见问题、排查方法和解决方案。

## 1. 数据源概述

财联社数据源包括两个主要组件：
- `cls`: 财联社电报页面抓取
- `cls-article`: 财联社文章页面抓取

这两个数据源设计为使用多种抓取方法，按照以下优先级尝试：
1. 直接API (`use_direct_api`): 使用财联社官方API
2. 网页抓取 (`use_scraping`): 直接抓取财联社网页内容
3. 备用API (`use_backup_api`): 使用备用API方法
4. Selenium抓取 (`use_selenium`): 使用浏览器模拟访问（当其他方法失败时的后备方案）

**当前配置**：
- `use_selenium`: True (启用)
- `use_direct_api`: False (禁用)
- `use_scraping`: True (启用)
- `use_backup_api`: True (启用)

**注意**：2025年3月23日的检测表明，Selenium抓取能够可靠地获取财联社电报内容，即使在其他方法失败的情况下。因此，我们已启用Selenium功能作为备份方案。

## 2. 常见故障及解决方案

### 2.1 数据源状态为ERROR

**症状**：数据库中源状态为`ERROR`

**排查步骤**：
1. 检查`sources`表中的`last_error`字段了解具体错误信息
2. 运行测试脚本验证源健康状态：
   ```bash
   cd backend
   python test_cls_telegraph.py
   ```

**常见原因及解决方案**：

| 错误类型 | 可能原因 | 解决方案 |
|---------|---------|---------|
| 网络连接错误 | 服务器网络问题或目标站点封锁 | 检查网络连接，必要时更换IP或使用代理 |
| 解析错误 | 网站结构变化 | 更新正则表达式或抓取逻辑，参考下文修复方法 |
| API限制 | 请求过于频繁触发限制 | 调整请求间隔，确保配置为使用多种抓取方式 |
| Selenium错误 | WebDriver配置问题或Chrome浏览器问题 | 检查chromedriver和Chrome版本是否匹配，确保Chrome依赖已安装 |

### 2.2 网站结构变化导致抓取失败

**症状**：日志中出现正则匹配失败或内容解析错误

**解决方案**：
1. 网站结构变化时，使用正则提取作为备选方案：
   ```python
   # regex_pattern定义在CLSNewsSource类中，可根据网站变化进行调整
   # 查看CLSNewsSource._extract_telegraph_with_regex方法了解实现
   ```

2. 更新正则表达式以适应新结构：
   ```python
   # 常用的正则表达式
   r'"content":"(.*?)","in_roll"'  # 匹配电报内容
   r'"title":"(.*?)","content"'    # 匹配电报标题
   ```

3. 如果其他方法均失败，Selenium通常能够可靠抓取内容：
   - 确保`use_selenium`设置为`True`
   - 检查Chrome和chromedriver是否正确安装

### 2.3 Selenium相关问题

**症状**：日志中出现`WebDriverException`或`Selenium错误`

**排查步骤**：
1. 运行Selenium测试脚本验证：
   ```bash
   cd /home/losesky/HeatLink
   python check_cls_with_selenium.py
   ```

2. 检查Chrome和chromedriver是否正确安装：
   ```bash
   chromedriver --version
   google-chrome --version
   ```

3. 确保版本匹配，必要时更新：
   ```bash
   # 更新chromedriver
   apt-get update && apt-get install -y chromium-chromedriver
   ```

## 3. 数据源维护工具

### 3.1 健康检查脚本

自动检查并修复财联社数据源：

```bash
cd backend
python check_sources_health.py
```

**定时执行**：
可通过crontab设置定期执行：

```bash
# 安装定时任务
cd backend
bash install_crontab.sh
```

### 3.2 错误信息清理脚本

清理错误信息并恢复源状态：

```bash
cd backend
python update_cls_error_info.py
```

### 3.3 Selenium测试脚本

检查Selenium抓取功能是否正常：

```bash
cd /home/losesky/HeatLink
python check_cls_with_selenium.py
```

## 4. 手动修复步骤

如果自动修复失败，可按以下步骤手动修复：

1. 修改数据源配置（启用Selenium）：
   ```sql
   UPDATE sources 
   SET config = '{"use_selenium": true, "use_direct_api": false, "use_scraping": true, "use_backup_api": true}' 
   WHERE id = 'cls';
   
   UPDATE sources 
   SET config = '{"use_selenium": true, "use_direct_api": false, "use_scraping": true, "use_backup_api": true}' 
   WHERE id = 'cls-article';
   ```

2. 更新源状态和类型：
   ```sql
   UPDATE sources 
   SET status = 'ACTIVE', type = 'WEB', last_error = NULL 
   WHERE id IN ('cls', 'cls-article');
   ```

3. 验证修复结果：
   ```sql
   SELECT id, name, status, type, config, last_error 
   FROM sources 
   WHERE id LIKE 'cls%';
   ```

## 5. 数据源调试

### 5.1 测试正则提取功能

```bash
cd backend
python test_cls_telegraph.py --test_regex_only
```

### 5.2 测试Selenium功能

```bash
cd /home/losesky/HeatLink
python check_cls_with_selenium.py
```

### 5.3 查看抓取历史

```bash
ls -la backend/worker/sources/sites/cls_*_results_*.json
```

### 5.4 抓取结果分析

分析最新抓取结果：

```bash
cd backend
python -c "import json; f=sorted(glob.glob('worker/sources/sites/cls_*_results_*.json'))[-1]; print(json.dumps(json.load(open(f)), indent=2, ensure_ascii=False)[:500])"
```

## 6. 预防措施

1. 设置正确的源类型和配置：
   - 确保源类型为`WEB`
   - 配置文件中启用多种抓取方式，包括Selenium
   - 保持Selenium作为备用选项启用

2. 定期检查源健康状态：
   - 通过定时任务自动运行健康检查
   - 配置邮件通知（通过`install_crontab.sh`设置）

3. 保持测试脚本和文档更新：
   - 网站结构变化时更新测试脚本
   - 将新发现的问题和解决方案添加到本文档
   - 定期测试Selenium功能是否正常

## 7. 联系方式

如遇到未能解决的问题，请联系维护人员：

- 技术支持：[添加联系人邮箱]
- 项目维护：[添加项目负责人]

---

*最后更新日期: 2025-03-23* 