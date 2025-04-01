#!/bin/bash

# 测试第一财经新闻适配器的脚本

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 设置日志文件
LOG_DIR="../logs"
mkdir -p $LOG_DIR
LOG_FILE="$LOG_DIR/yicai_test_$(date +%Y%m%d_%H%M%S).log"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}    测试第一财经新闻适配器${NC}"
echo -e "${BLUE}=========================================${NC}"

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 切换到backend目录
cd ..

# 函数: 检查Python环境
check_python() {
    echo -e "${BLUE}[+] 检查Python环境...${NC}"
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}错误: 未找到python3命令${NC}"
        echo -e "${YELLOW}请确保已安装Python 3.7+${NC}"
        exit 1
    fi
    
    # 检查Python版本
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}[√] 使用Python版本: $PY_VERSION${NC}"
    
    # 检查虚拟环境
    if [ -d "venv" ]; then
        echo -e "${BLUE}[+] 激活虚拟环境...${NC}"
        source venv/bin/activate
    elif [ -d "../venv" ]; then
        echo -e "${BLUE}[+] 激活上级目录虚拟环境...${NC}"
        source ../venv/bin/activate
    else
        echo -e "${YELLOW}[!] 未找到虚拟环境，使用系统Python${NC}"
    fi
}

# 函数: 检查环境变量
check_env() {
    echo -e "${BLUE}[+] 检查环境变量配置...${NC}"
    if [ ! -f ".env" ]; then
        echo -e "${RED}[!] 警告: 未找到.env文件${NC}"
        echo -e "${YELLOW}[!] 是否继续测试? (y/n)${NC}"
        read -r answer
        if [[ ! "$answer" =~ ^[Yy]$ ]]; then
            echo -e "${RED}[!] 退出测试${NC}"
            exit 1
        fi
    else
        echo -e "${BLUE}[+] 尝试修复.env文件可能的格式问题...${NC}"
        python3 tests/fix_env.py
        
        echo -e "${GREEN}[√] 找到.env文件，加载环境变量${NC}"
        set -a
        source .env
        set +a
        echo -e "${GREEN}[√] 数据库连接: ${DATABASE_URL}${NC}"
        
        # 下面的CORS_ORIGINS检查可以保留，以防修复脚本未能完全解决问题
        if [[ -n "$CORS_ORIGINS" ]]; then
            # 判断是否是有效的JSON数组格式
            if ! python3 -c "import json; json.loads('$CORS_ORIGINS')" &>/dev/null; then
                echo -e "${YELLOW}[!] 警告: CORS_ORIGINS格式仍有问题${NC}"
                echo -e "${YELLOW}[!] 当前值: $CORS_ORIGINS${NC}"
                echo -e "${YELLOW}[!] 是否尝试手动修复? (y/n)${NC}"
                read -r fix_answer
                if [[ "$fix_answer" =~ ^[Yy]$ ]]; then
                    # 尝试修复CORS_ORIGINS格式
                    # 移除可能的换行符和不正确的空格
                    FIXED_CORS=$(echo "$CORS_ORIGINS" | tr -d '\n' | sed 's/\s\+/ /g')
                    # 生成正确的JSON数组字符串
                    export CORS_ORIGINS="[\"$(echo "$FIXED_CORS" | grep -oE 'http[^"]*' | paste -sd '","' -)\"]"
                    echo -e "${GREEN}[√] 修复后的CORS_ORIGINS: $CORS_ORIGINS${NC}"
                fi
            else
                echo -e "${GREEN}[√] CORS_ORIGINS格式正确${NC}"
            fi
        fi
    fi
}

# 函数: 检查依赖
check_dependencies() {
    echo -e "${BLUE}[+] 检查测试依赖...${NC}"
    python3 -c "
try:
    import fastapi
    import sqlalchemy
    from selenium import webdriver
    from bs4 import BeautifulSoup
    print('${GREEN}[√] 核心依赖检查通过${NC}')
except ImportError as e:
    print('${RED}[!] 缺少依赖: ' + str(e) + '${NC}')
    print('${YELLOW}[!] 请确保安装了所有必要的依赖${NC}')
    exit(1)
"
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}[!] 依赖检查失败，是否继续? (y/n)${NC}"
        read -r answer
        if [[ ! "$answer" =~ ^[Yy]$ ]]; then
            echo -e "${RED}[!] 退出测试${NC}"
            exit 1
        fi
    fi
}

# 函数: 获取第一财经新闻页面HTML
fetch_yicai_html() {
    echo -e "${BLUE}[+] 获取第一财经新闻页面HTML...${NC}"
    
    # 检查curl命令
    if ! command -v curl &> /dev/null; then
        echo -e "${YELLOW}[!] 未找到curl命令，跳过HTML获取${NC}"
        return 1
    fi
    
    # 设置输出文件
    HTML_FILE="tests/yicai_news_page.html"
    
    # 使用curl获取页面
    echo -e "${BLUE}[+] 正在获取页面...${NC}"
    USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    curl -s -A "$USER_AGENT" "https://www.yicai.com/news/" > "$HTML_FILE"
    
    # 检查是否成功获取
    if [ $? -eq 0 ] && [ -s "$HTML_FILE" ]; then
        echo -e "${GREEN}[√] 成功获取页面，保存到 $HTML_FILE${NC}"
        return 0
    else
        echo -e "${RED}[!] 获取页面失败${NC}"
        return 1
    fi
}

# 函数: 检查数据库依赖
check_database() {
    echo -e "${BLUE}[+] 检查数据库依赖...${NC}"
    
    # 检查数据库配置
    if [[ -n "$DATABASE_URL" ]]; then
        echo -e "${GREEN}[√] 数据库配置: ${DATABASE_URL}${NC}"
        
        # 确保数据源记录存在
        echo -e "${BLUE}[+] 确保数据库中存在必要的数据源记录...${NC}"
        python3 tests/ensure_sources.py
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}[√] 数据源记录检查/创建成功${NC}"
        else
            echo -e "${RED}[!] 数据源记录检查/创建失败${NC}"
            echo -e "${YELLOW}[!] 继续测试可能会导致外键约束错误${NC}"
            echo -e "${YELLOW}[!] 是否继续测试? (y/n)${NC}"
            read -r answer
            if [[ ! "$answer" =~ ^[Yy]$ ]]; then
                echo -e "${RED}[!] 退出测试${NC}"
                exit 1
            fi
        fi
    else
        echo -e "${YELLOW}[!] 警告: 未找到数据库配置${NC}"
        echo -e "${YELLOW}[!] 保存数据库测试可能会失败${NC}"
    fi
}

# 主测试函数
run_tests() {
    echo ""
    echo -e "${BLUE}[+] 开始运行测试...${NC}"
    
    # 1. 运行HTML解析测试
    echo -e "${BLUE}[+] 是否运行HTML解析测试? [Y/n]${NC}"
    read -r run_html_test
    
    if [[ ! "$run_html_test" =~ ^[Nn]$ ]]; then
        echo -e "${BLUE}[+] 运行HTML解析测试...${NC}"
        
        # 尝试获取第一财经页面HTML
        fetch_yicai_html
        HTML_FETCH_RESULT=$?
        
        if [ $HTML_FETCH_RESULT -eq 0 ]; then
            # 使用获取的HTML文件运行测试
            python3 tests/test_yicai_html.py tests/yicai_news_page.html 2>&1 | tee -a "$LOG_FILE"
        else
            # 使用内置的样例HTML运行测试
            python3 tests/test_yicai_html.py 2>&1 | tee -a "$LOG_FILE"
        fi
        
        HTML_TEST_RESULT=${PIPESTATUS[0]}
        
        if [ $HTML_TEST_RESULT -eq 0 ]; then
            echo -e "${GREEN}[√] HTML解析测试成功完成${NC}"
        else
            echo -e "${RED}[!] HTML解析测试失败，返回代码: $HTML_TEST_RESULT${NC}"
            echo -e "${YELLOW}[!] 详细日志已保存到: $LOG_FILE${NC}"
        fi
        
        echo ""
        echo -e "${BLUE}=========================================${NC}"
    else
        echo -e "${YELLOW}[!] 跳过HTML解析测试${NC}"
    fi
    
    # 2. 运行特定HTML结构测试
    echo -e "${BLUE}[+] 是否运行特定HTML结构测试? [Y/n]${NC}"
    read -r run_specific_test
    
    if [[ ! "$run_specific_test" =~ ^[Nn]$ ]]; then
        echo -e "${BLUE}[+] 运行特定HTML结构测试...${NC}"
        python3 tests/test_yicai_specific.py 2>&1 | tee -a "$LOG_FILE"
        SPECIFIC_TEST_RESULT=${PIPESTATUS[0]}
        
        if [ $SPECIFIC_TEST_RESULT -eq 0 ]; then
            echo -e "${GREEN}[√] 特定HTML结构测试成功完成${NC}"
        else
            echo -e "${RED}[!] 特定HTML结构测试失败，返回代码: $SPECIFIC_TEST_RESULT${NC}"
            echo -e "${YELLOW}[!] 详细日志已保存到: $LOG_FILE${NC}"
        fi
        
        echo ""
        echo -e "${BLUE}=========================================${NC}"
    else
        echo -e "${YELLOW}[!] 跳过特定HTML结构测试${NC}"
    fi
    
    # 3. 运行简单获取数据测试
    echo -e "${BLUE}[+] 是否运行数据获取测试? [Y/n]${NC}"
    read -r run_fetch_test
    
    if [[ ! "$run_fetch_test" =~ ^[Nn]$ ]]; then
        echo -e "${BLUE}[+] 运行数据获取测试...${NC}"
        python3 tests/test_yicai_fetch.py 2>&1 | tee -a "$LOG_FILE"
        FETCH_RESULT=${PIPESTATUS[0]}

        if [ $FETCH_RESULT -eq 0 ]; then
            echo -e "${GREEN}[√] 数据获取测试成功完成${NC}"
        else
            echo -e "${RED}[!] 数据获取测试失败，返回代码: $FETCH_RESULT${NC}"
            echo -e "${YELLOW}[!] 详细日志已保存到: $LOG_FILE${NC}"
        fi

        echo ""
        echo -e "${BLUE}=========================================${NC}"
    else
        echo -e "${YELLOW}[!] 跳过数据获取测试${NC}"
    fi

    # 4. 询问是否运行数据库保存测试
    echo -e "${BLUE}[+] 是否运行数据库保存测试? [y/N]${NC}"
    read -r run_db_test

    if [[ $run_db_test =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}[+] 运行数据库保存测试...${NC}"
        python3 tests/test_yicai.py 2>&1 | tee -a "$LOG_FILE"
        DB_RESULT=${PIPESTATUS[0]}
        
        if [ $DB_RESULT -eq 0 ]; then
            echo -e "${GREEN}[√] 数据库保存测试成功完成${NC}"
        else
            echo -e "${RED}[!] 数据库保存测试失败，返回代码: $DB_RESULT${NC}"
            echo -e "${YELLOW}[!] 详细日志已保存到: $LOG_FILE${NC}"
        fi
    else
        echo -e "${YELLOW}[!] 跳过数据库保存测试${NC}"
    fi
}

# 主函数
main() {
    check_python
    check_env
    check_dependencies
    check_database
    run_tests
    
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${GREEN}[√] 所有测试完成!${NC}"
    echo -e "${GREEN}[√] 详细日志已保存到: $LOG_FILE${NC}"
}

# 异常处理
trap 'echo -e "${RED}[!] 脚本执行被中断${NC}"; exit 1' INT TERM

# 执行主函数
main

exit 0 