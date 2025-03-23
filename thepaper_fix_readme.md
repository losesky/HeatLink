# 澎湃新闻(ThePaper)数据源修复

## 问题描述

系统中存在两个数据源ID同时指向澎湃新闻(The Paper)的数据源:
1. `thepaper`: 原配置为API类型，使用第三方API获取数据
2. `thepaper_selenium`: 配置为WEB类型，使用Selenium模拟浏览器爬取数据

但由于实际两个源都通过Selenium返回正确数据，这表明工厂类中的配置使这两个ID都实例化为相同的Selenium爬虫类，导致数据冗余。

## 原因分析

在`worker/sources/factory.py`中，我们发现以下代码：

```python
elif source_type == "thepaper" or source_type == "thepaper-selenium" or source_type == "thepaper_selenium":
    return ThePaperSeleniumSource(**kwargs)
```

这段代码将三种不同的source_type(`thepaper`, `thepaper-selenium`, `thepaper_selenium`)都映射到`ThePaperSeleniumSource`类。当调用工厂方法创建源时，无论是使用"thepaper"还是"thepaper_selenium"，都会创建一个ThePaperSeleniumSource实例。

然而，每个实例在创建时保留了自己的source_id，这导致两个不同ID指向相同功能的源，从而在数据库中产生两组冗余数据。

## 修复步骤

1. **数据库修复** (`fix_thepaper_source.py`):
   - 将`thepaper`源的类型从API更新为WEB
   - 将所有`thepaper_selenium`源的新闻项迁移到`thepaper`源
   - 删除冗余的`thepaper_selenium`源

2. **源工厂修复** (`worker/sources/factory.py`):
   - 修改源工厂类，强制将任何`thepaper`相关源的source_id统一为`thepaper`
   - 添加警告日志，标记ID被重写的情况

3. **初始化脚本修复** (`scripts/init_sources.py`):
   - 更新初始化脚本中`thepaper`源的配置，将其类型从API改为WEB
   - 移除API相关配置，使用空配置对象

## 验证结果

验证脚本(`verify_thepaper_fix.py`)确认:
- `thepaper`源现在正确配置为WEB类型
- `ThePaperSeleniumSource`类能够成功抓取数据
- 数据库中没有冗余的`thepaper_selenium`源
- 所有新闻数据都统一使用`thepaper`源标识符

## 防止问题重现

修复后的代码确保:
1. 无论使用哪种相关的source_type，都会强制使用`thepaper`作为source_id
2. 源工厂在ID冲突时会记录警告日志
3. 初始化脚本正确设置源类型

这确保了即使未来添加不同的源类型，也不会出现ID冲突和数据冗余问题。 