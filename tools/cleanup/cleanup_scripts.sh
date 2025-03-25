#!/bin/bash

# HeatLink 维护脚本整理工具
# 此脚本将项目中散布的维护脚本整合到统一的目录结构中

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 维护脚本整理工具   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 创建目标目录结构
echo -e "${YELLOW}正在创建目录结构...${NC}"
mkdir -p tools/data_sources
mkdir -p tools/database
mkdir -p tools/diagnostics
mkdir -p tools/deprecated

# 复制文件到适当的目录，使用cp而不是mv以保留原始文件
echo -e "${YELLOW}正在整理数据源监控工具...${NC}"
if [ -f ./backend/check_sources_health.py ]; then
    cp ./backend/check_sources_health.py ./tools/data_sources/
    echo "复制 check_sources_health.py 到 tools/data_sources/"
fi

if [ -f ./check_cls_api.py ]; then
    cp ./check_cls_api.py ./tools/data_sources/
    echo "复制 check_cls_api.py 到 tools/data_sources/"
fi

if [ -f ./check_cls_with_selenium.py ]; then
    cp ./check_cls_with_selenium.py ./tools/data_sources/
    echo "复制 check_cls_with_selenium.py 到 tools/data_sources/"
fi

if [ -f ./check_thepaper_structure.py ]; then
    cp ./check_thepaper_structure.py ./tools/data_sources/
    echo "复制 check_thepaper_structure.py 到 tools/data_sources/"
fi

if [ -f ./verify_thepaper_fix.py ]; then
    cp ./verify_thepaper_fix.py ./tools/data_sources/
    echo "复制 verify_thepaper_fix.py 到 tools/data_sources/"
fi

if [ -f ./fix_thepaper_source.py ]; then
    cp ./fix_thepaper_source.py ./tools/data_sources/
    echo "复制 fix_thepaper_source.py 到 tools/data_sources/"
fi

echo -e "${YELLOW}正在整理数据库维护工具...${NC}"
if [ -f ./fix_database.sh ]; then
    cp ./fix_database.sh ./tools/database/
    echo "复制 fix_database.sh 到 tools/database/"
fi

if [ -f ./backend/fix_categories.py ]; then
    cp ./backend/fix_categories.py ./tools/database/
    echo "复制 fix_categories.py 到 tools/database/"
fi

if [ -f ./backend/scripts/verify_data.py ]; then
    cp ./backend/scripts/verify_data.py ./tools/database/
    echo "复制 verify_data.py 到 tools/database/"
fi

# 复制MAINTENANCE_SCRIPTS_REPORT.md到tools目录作为文档
if [ -f ./MAINTENANCE_SCRIPTS_REPORT.md ]; then
    cp ./MAINTENANCE_SCRIPTS_REPORT.md ./tools/
    echo "复制 MAINTENANCE_SCRIPTS_REPORT.md 到 tools/"
fi

# 创建README文件
echo -e "${YELLOW}创建README文件...${NC}"

cat > ./tools/README.md << 'EOL'
# HeatLink 维护工具集

此目录包含HeatLink项目的各种维护工具和脚本，用于系统监控、诊断和修复。

## 目录结构

- `data_sources/`: 数据源监控和修复工具
- `database/`: 数据库维护和修复工具
- `diagnostics/`: 系统诊断工具
- `deprecated/`: 已弃用但保留作参考的工具

## 使用指南

请参阅每个工具的内部文档或头部注释了解具体用法。大多数Python脚本可以直接运行：

```bash
python tools/data_sources/check_sources_health.py
```

Bash脚本通常需要添加执行权限：

```bash
chmod +x tools/database/fix_database.sh
./tools/database/fix_database.sh
```

## 文档

完整的维护脚本报告和建议请参阅 `MAINTENANCE_SCRIPTS_REPORT.md`。
EOL

echo "创建 tools/README.md"

# 给所有脚本添加执行权限
echo -e "${YELLOW}添加执行权限...${NC}"
find ./tools -name "*.py" -exec chmod +x {} \;
find ./tools -name "*.sh" -exec chmod +x {} \;

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}维护脚本整理完成!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "注意：原始脚本未被删除，仅复制到新目录结构。"
echo -e "您可以在验证新结构工作正常后，手动删除原始脚本。"
echo -e "新的维护工具目录位于: ${YELLOW}./tools/${NC}"
echo -e "${GREEN}=======================================${NC}" 