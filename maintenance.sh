#!/bin/bash

# HeatLink 项目统一维护脚本
# 此脚本整合了项目维护、清理和组织功能

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 脚本版本
VERSION="1.0.0"

# 默认选项
ORGANIZE=false
CLEANUP=false
CLEAN_LOGS=false
ORGANIZE_TESTS=false
REMOVE_REDUNDANT=false
INTERACTIVE=true
ALL=false

# 显示帮助信息
show_help() {
    echo -e "${BLUE}HeatLink 项目维护工具 v${VERSION}${NC}"
    echo "使用方法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help              显示此帮助信息"
    echo "  -o, --organize          整理维护脚本到tools目录"
    echo "  -c, --cleanup           清理临时文件和缓存"
    echo "  -l, --clean-logs        清理7天前的日志文件"
    echo "  -t, --organize-tests    整理测试文件到tests目录"
    echo "  -r, --remove-redundant  删除已整理到tools目录的冗余脚本"
    echo "  -a, --all               执行所有维护操作"
    echo "  -n, --non-interactive   非交互模式，使用默认选项"
    echo ""
    echo "示例:"
    echo "  $0                       进入交互式菜单"
    echo "  $0 --organize --cleanup  整理脚本并清理临时文件"
    echo "  $0 --all                 执行所有维护操作"
}

# 解析命令行参数
parse_args() {
    # 如果没有参数，默认使用交互模式
    if [ $# -eq 0 ]; then
        INTERACTIVE=true
        return
    fi

    INTERACTIVE=false
    while [ "$1" != "" ]; do
        case $1 in
            -h | --help )          show_help
                                   exit
                                   ;;
            -o | --organize )      ORGANIZE=true
                                   ;;
            -c | --cleanup )       CLEANUP=true
                                   ;;
            -l | --clean-logs )    CLEAN_LOGS=true
                                   ;;
            -t | --organize-tests ) ORGANIZE_TESTS=true
                                   ;;
            -r | --remove-redundant ) REMOVE_REDUNDANT=true
                                   ;;
            -a | --all )           ALL=true
                                   ;;
            -n | --non-interactive ) INTERACTIVE=false
                                   ;;
            * )                    echo "未知选项: $1"
                                   show_help
                                   exit 1
        esac
        shift
    done

    # 如果指定了--all，设置所有选项为true
    if [ "$ALL" = true ]; then
        ORGANIZE=true
        CLEANUP=true
        CLEAN_LOGS=true
        ORGANIZE_TESTS=true
        REMOVE_REDUNDANT=true
    fi
}

# 显示交互式菜单
show_menu() {
    clear
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}     HeatLink 项目维护工具 v${VERSION}    ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo
    echo -e "1) ${GREEN}整理维护脚本${NC} - 将维护脚本组织到tools目录"
    echo -e "2) ${GREEN}清理临时文件${NC} - 清理缓存和临时文件"
    echo -e "3) ${GREEN}清理日志文件${NC} - 删除7天前的日志文件"
    echo -e "4) ${GREEN}整理测试文件${NC} - 将测试文件移动到tests目录"
    echo -e "5) ${GREEN}删除冗余脚本${NC} - 删除已整理的原始脚本"
    echo -e "6) ${GREEN}执行所有操作${NC} - 运行以上所有维护任务"
    echo
    echo -e "0) ${RED}退出${NC}"
    echo
    echo -n "请选择操作 [0-6]: "
    read -r choice

    case $choice in
        1) ORGANIZE=true ;;
        2) CLEANUP=true ;;
        3) CLEAN_LOGS=true ;;
        4) ORGANIZE_TESTS=true ;;
        5) REMOVE_REDUNDANT=true ;;
        6) ORGANIZE=true
           CLEANUP=true
           CLEAN_LOGS=true
           ORGANIZE_TESTS=true
           REMOVE_REDUNDANT=true ;;
        0) echo "退出"
           exit 0 ;;
        *) echo -e "${RED}无效的选择${NC}"
           sleep 2
           show_menu ;;
    esac
}

# 函数：整理维护脚本到tools目录
organize_scripts() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}   整理维护脚本到tools目录   ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    
    # 创建目录结构
    echo -e "${YELLOW}创建目录结构...${NC}"
    mkdir -p tools/data_sources
    mkdir -p tools/database
    mkdir -p tools/system
    mkdir -p tools/celery
    mkdir -p tools/diagnostics
    mkdir -p tools/deprecated
    mkdir -p tools/reports
    mkdir -p tools/cleanup
    
    # 检查现有tools目录是否已经存在并有文件
    if [ -d "tools" ] && [ "$(ls -A tools/data_sources 2>/dev/null)" ]; then
        echo -e "${YELLOW}工具目录已存在并包含文件，将只添加缺失的工具${NC}"
        EXISTING_TOOLS=true
    else
        EXISTING_TOOLS=false
    fi
    
    # 复制数据源监控工具
    echo -e "${YELLOW}整理数据源监控工具...${NC}"
    if [ -f "./backend/check_sources_health.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/data_sources/check_sources_health.py" ]; }; then
        cp ./backend/check_sources_health.py ./tools/data_sources/
        echo "复制 check_sources_health.py 到 tools/data_sources/"
    fi
    
    if [ -f "./check_cls_api.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/data_sources/check_cls_api.py" ]; }; then
        cp ./check_cls_api.py ./tools/data_sources/
        echo "复制 check_cls_api.py 到 tools/data_sources/"
    fi
    
    if [ -f "./check_cls_with_selenium.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/data_sources/check_cls_with_selenium.py" ]; }; then
        cp ./check_cls_with_selenium.py ./tools/data_sources/
        echo "复制 check_cls_with_selenium.py 到 tools/data_sources/"
    fi
    
    if [ -f "./check_thepaper_structure.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/data_sources/check_thepaper_structure.py" ]; }; then
        cp ./check_thepaper_structure.py ./tools/data_sources/
        echo "复制 check_thepaper_structure.py 到 tools/data_sources/"
    fi
    
    if [ -f "./verify_thepaper_fix.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/data_sources/verify_thepaper_fix.py" ]; }; then
        cp ./verify_thepaper_fix.py ./tools/data_sources/
        echo "复制 verify_thepaper_fix.py 到 tools/data_sources/"
    fi
    
    if [ -f "./fix_thepaper_source.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/data_sources/fix_thepaper_source.py" ]; }; then
        cp ./fix_thepaper_source.py ./tools/data_sources/
        echo "复制 fix_thepaper_source.py 到 tools/data_sources/"
    fi
    
    # 整理数据库维护工具
    echo -e "${YELLOW}整理数据库维护工具...${NC}"
    if [ -f "./fix_database.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/database/fix_database.sh" ]; }; then
        cp ./fix_database.sh ./tools/database/
        echo "复制 fix_database.sh 到 tools/database/"
    fi
    
    if [ -f "./backend/fix_categories.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/database/fix_categories.py" ]; }; then
        cp ./backend/fix_categories.py ./tools/database/
        echo "复制 fix_categories.py 到 tools/database/"
    fi
    
    if [ -f "./backend/scripts/verify_data.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/database/verify_data.py" ]; }; then
        cp ./backend/scripts/verify_data.py ./tools/database/
        echo "复制 verify_data.py 到 tools/database/"
    fi
    
    if [ -f "./backend/scripts/create_admin.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/database/create_admin.py" ]; }; then
        cp ./backend/scripts/create_admin.py ./tools/database/
        echo "复制 create_admin.py 到 tools/database/"
    fi
    
    # 整理系统维护工具
    echo -e "${YELLOW}整理系统维护工具...${NC}"
    if [ -f "./health_check.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/system/health_check.sh" ]; }; then
        cp ./health_check.sh ./tools/system/
        echo "复制 health_check.sh 到 tools/system/"
    fi
    
    if [ -f "./local-dev.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/system/local-dev.sh" ]; }; then
        cp ./local-dev.sh ./tools/system/
        echo "复制 local-dev.sh 到 tools/system/"
    fi
    
    # 整理Celery相关工具
    echo -e "${YELLOW}整理Celery工具...${NC}"
    if [ -f "./run_celery.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/celery/run_celery.sh" ]; }; then
        cp ./run_celery.sh ./tools/celery/
        echo "复制 run_celery.sh 到 tools/celery/"
    fi
    
    if [ -f "./stop_celery.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/celery/stop_celery.sh" ]; }; then
        cp ./stop_celery.sh ./tools/celery/
        echo "复制 stop_celery.sh 到 tools/celery/"
    fi
    
    if [ -f "./run_task.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/celery/run_task.py" ]; }; then
        cp ./run_task.py ./tools/celery/
        echo "复制 run_task.py 到 tools/celery/"
    fi
    
    if [ -f "./monitor_tasks.py" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/celery/monitor_tasks.py" ]; }; then
        cp ./monitor_tasks.py ./tools/celery/
        echo "复制 monitor_tasks.py 到 tools/celery/"
    fi
    
    # 整理清理工具
    echo -e "${YELLOW}整理清理工具...${NC}"
    if [ -f "./cleanup.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/cleanup/cleanup.sh" ]; }; then
        cp ./cleanup.sh ./tools/cleanup/
        echo "复制 cleanup.sh 到 tools/cleanup/"
    fi
    
    if [ -f "./cleanup_scripts.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/cleanup/cleanup_scripts.sh" ]; }; then
        cp ./cleanup_scripts.sh ./tools/cleanup/
        echo "复制 cleanup_scripts.sh 到 tools/cleanup/"
    fi
    
    if [ -f "./apply_unified_readme.sh" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/cleanup/apply_unified_readme.sh" ]; }; then
        cp ./apply_unified_readme.sh ./tools/cleanup/
        echo "复制 apply_unified_readme.sh 到 tools/cleanup/"
    fi
    
    # 复制文档和报告
    if [ -f "./MAINTENANCE_SCRIPTS_REPORT.md" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/reports/MAINTENANCE_SCRIPTS_REPORT.md" ]; }; then
        cp ./MAINTENANCE_SCRIPTS_REPORT.md ./tools/reports/
        echo "复制 MAINTENANCE_SCRIPTS_REPORT.md 到 tools/reports/"
    fi
    
    if [ -f "./FILE_ORGANIZATION.md" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/reports/FILE_ORGANIZATION.md" ]; }; then
        cp ./FILE_ORGANIZATION.md ./tools/reports/
        echo "复制 FILE_ORGANIZATION.md 到 tools/reports/"
    fi
    
    if [ -f "./backend/DATA_MIGRATION.md" ] && { [ "$EXISTING_TOOLS" = false ] || [ ! -f "./tools/reports/DATA_MIGRATION.md" ]; }; then
        cp ./backend/DATA_MIGRATION.md ./tools/reports/
        echo "复制 DATA_MIGRATION.md 到 tools/reports/"
    fi
    
    # 创建或更新README文件
    echo -e "${YELLOW}更新README文件...${NC}"
    
    cat > ./tools/README.md << 'EOL'
# HeatLink 维护工具集

此目录包含HeatLink项目的各种维护工具和脚本，用于系统监控、诊断和修复。

## 目录结构

- `data_sources/`: 数据源监控和修复工具
- `database/`: 数据库维护和修复工具
- `system/`: 系统维护和健康检查工具
- `celery/`: Celery任务和进程管理工具
- `cleanup/`: 项目清理和整理工具
- `diagnostics/`: 系统诊断工具
- `reports/`: 项目文档和报告
- `deprecated/`: 已弃用但保留作参考的工具

## 使用指南

### 数据源工具

```bash
# 检查数据源健康状态
python tools/data_sources/check_sources_health.py

# 验证特定数据源修复
python tools/data_sources/verify_thepaper_fix.py
```

### 数据库工具

```bash
# 修复数据库
chmod +x tools/database/fix_database.sh
./tools/database/fix_database.sh

# 验证数据完整性
python tools/database/verify_data.py verify
```

### 系统工具

```bash
# 健康检查
chmod +x tools/system/health_check.sh
./tools/system/health_check.sh
```

### Celery工具

```bash
# 启动Celery服务
chmod +x tools/celery/run_celery.sh
./tools/celery/run_celery.sh

# 停止Celery服务
chmod +x tools/celery/stop_celery.sh
./tools/celery/stop_celery.sh

# 监控任务
python tools/celery/monitor_tasks.py
```

### 清理工具

```bash
# 清理项目临时文件
chmod +x tools/cleanup/cleanup.sh
./tools/cleanup/cleanup.sh
```

## 文档

完整的项目文档请参阅 `reports/` 目录下的文件。
EOL
    
    echo "更新 tools/README.md"
    
    # 为所有脚本添加执行权限
    echo -e "${YELLOW}添加执行权限...${NC}"
    find ./tools -name "*.py" -exec chmod +x {} \;
    find ./tools -name "*.sh" -exec chmod +x {} \;
    
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}运维脚本整理完成!${NC}"
    echo -e "${GREEN}=====================================${NC}"
    
    # 创建一个清理冗余文件的脚本（如果不存在）
    if [ ! -f "./tools/cleanup/cleanup_redundant.sh" ]; then
        create_redundant_cleanup_script
    fi
}

# 创建清理冗余文件的脚本
create_redundant_cleanup_script() {
    cat > ./tools/cleanup/cleanup_redundant.sh << 'EOL'
#!/bin/bash

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}   HeatLink 冗余文件清理工具   ${NC}"
echo -e "${GREEN}=======================================${NC}"

# 确认操作
echo -e "${YELLOW}此操作将删除已经移动到tools目录的冗余脚本文件。${NC}"
read -p "确认要继续吗? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo -e "${YELLOW}操作已取消${NC}"
    exit 0
fi

# 删除根目录下已移动到tools的冗余文件
echo -e "${YELLOW}删除根目录下的冗余文件...${NC}"

redundant_files=(
    "./check_cls_api.py"
    "./check_cls_with_selenium.py"
    "./check_thepaper_structure.py"
    "./verify_thepaper_fix.py"
    "./fix_thepaper_source.py"
    "./fix_database.sh"
    "./health_check.sh"
    "./run_celery.sh"
    "./stop_celery.sh"
    "./run_task.py"
    "./monitor_tasks.py"
    "./cleanup_scripts.sh"
    "./apply_unified_readme.sh"
    "./MAINTENANCE_SCRIPTS_REPORT.md"
)

for file in "${redundant_files[@]}"; do
    if [ -f "$file" ]; then
        rm "$file"
        echo "已删除: $file"
    fi
done

# 确保不删除正在运行的cleanup.sh
if [ -f "./cleanup.sh" ] && [ "$(basename "$(readlink -f "$0")")" != "cleanup.sh" ]; then
    rm "./cleanup.sh"
    echo "已删除: ./cleanup.sh"
fi

echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN}冗余文件清理完成!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo -e "所有维护工具现在位于 ${YELLOW}./tools/${NC} 目录下。"
echo -e "${GREEN}=======================================${NC}"
EOL

    chmod +x ./tools/cleanup/cleanup_redundant.sh
    echo "创建冗余文件清理脚本: tools/cleanup/cleanup_redundant.sh"
}

# 函数：清理临时文件
cleanup_temp_files() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}   清理临时文件和缓存   ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    
    # 清理Python缓存文件
    echo -e "${YELLOW}清理Python缓存文件...${NC}"
    find . -name "__pycache__" -type d -exec rm -rf {} +
    find . -name "*.pyc" -delete
    
    # 清理临时文件
    echo -e "${YELLOW}清理临时文件...${NC}"
    rm -f celery.pid
    rm -f backend/celerybeat-schedule
    rm -f backend/*.html
    rm -f backend/*.json
    
    # 清理其他临时文件
    rm -f .db_connection.json
    rm -f .migration_status.txt
    rm -f .data_status.json
    
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}临时文件清理完成!${NC}"
    echo -e "${GREEN}=====================================${NC}"
}

# 函数：清理日志文件
cleanup_log_files() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}   清理日志文件   ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    
    # 确保logs目录存在
    if [ ! -d "logs" ]; then
        echo -e "${YELLOW}未找到logs目录${NC}"
        return
    fi
    
    # 清理7天前的日志文件
    echo -e "${YELLOW}清理7天前的日志文件...${NC}"
    find logs -name "*.log" -type f -mtime +7 -exec rm {} \;
    
    count=$(find logs -name "*.log" -type f -mtime +7 | wc -l)
    if [ $count -eq 0 ]; then
        echo "未找到需要清理的日志文件"
    else
        echo "已删除 $count 个日志文件"
    fi
    
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}日志文件清理完成!${NC}"
    echo -e "${GREEN}=====================================${NC}"
}

# 函数：整理测试文件
organize_test_files() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}   整理测试文件   ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    
    # 确保tests目录存在
    mkdir -p tests
    
    echo -e "${YELLOW}整理测试文件...${NC}"
    find . -maxdepth 1 -name "test_*.py" -exec mv {} tests/ \;
    find . -maxdepth 1 -name "*_test.py" -exec mv {} tests/ \;
    
    count=$(find tests -name "test_*.py" -o -name "*_test.py" | wc -l)
    echo "tests目录中现有 $count 个测试文件"
    
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}测试文件整理完成!${NC}"
    echo -e "${GREEN}=====================================${NC}"
}

# 函数：删除冗余的脚本文件
remove_redundant_files() {
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${BLUE}   删除冗余脚本文件   ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    
    # 检查tools目录是否存在
    if [ ! -d "tools" ]; then
        echo -e "${RED}tools目录不存在，请先运行整理脚本功能${NC}"
        return
    fi
    
    # 列出要删除的冗余文件
    redundant_files=(
        "./check_cls_api.py"
        "./check_cls_with_selenium.py"
        "./check_thepaper_structure.py"
        "./verify_thepaper_fix.py"
        "./fix_thepaper_source.py"
        "./fix_database.sh"
        "./health_check.sh"
        "./run_celery.sh"
        "./stop_celery.sh"
        "./run_task.py"
        "./monitor_tasks.py"
        "./cleanup_scripts.sh"
        "./apply_unified_readme.sh"
        "./MAINTENANCE_SCRIPTS_REPORT.md"
        "./cleanup.sh"
        "./organize_maintenance_tools.sh"
    )
    
    # 如果是交互模式，询问确认
    if [ "$INTERACTIVE" = true ]; then
        echo -e "${YELLOW}以下文件将被删除:${NC}"
        for file in "${redundant_files[@]}"; do
            if [ -f "$file" ]; then
                echo "  $file"
            fi
        done
        
        echo
        read -p "确认删除这些文件? (y/n): " confirm
        if [ "$confirm" != "y" ]; then
            echo -e "${YELLOW}取消删除操作${NC}"
            return
        fi
    fi
    
    # 执行删除操作
    echo -e "${YELLOW}删除冗余文件...${NC}"
    for file in "${redundant_files[@]}"; do
        if [ -f "$file" ]; then
            rm "$file"
            echo "已删除: $file"
        fi
    done
    
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}冗余脚本文件删除完成!${NC}"
    echo -e "${GREEN}=====================================${NC}"
}

# 主函数
main() {
    # 解析命令行参数
    parse_args "$@"
    
    # 如果是交互模式，显示菜单
    if [ "$INTERACTIVE" = true ]; then
        show_menu
    fi
    
    # 执行选定的操作
    if [ "$ORGANIZE" = true ]; then
        organize_scripts
    fi
    
    if [ "$CLEANUP" = true ]; then
        cleanup_temp_files
    fi
    
    if [ "$CLEAN_LOGS" = true ]; then
        cleanup_log_files
    fi
    
    if [ "$ORGANIZE_TESTS" = true ]; then
        organize_test_files
    fi
    
    if [ "$REMOVE_REDUNDANT" = true ]; then
        remove_redundant_files
    fi
    
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}维护操作已完成!${NC}"
    echo -e "${GREEN}=====================================${NC}"
}

# 启动脚本
main "$@" 