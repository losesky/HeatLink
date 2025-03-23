#!/bin/bash
# 定期执行数据源健康检查脚本
# 使用方法：将此脚本添加到crontab中，例如：
# 0 */4 * * * /path/to/run_sources_health_check.sh

# 设置基本参数
DATE_TIME=$(date "+%Y-%m-%d %H:%M:%S")
LOG_PREFIX="[${DATE_TIME}]"
echo "${LOG_PREFIX} 开始执行源健康检查..."

# 设置脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "${LOG_PREFIX} 脚本目录: $SCRIPT_DIR"

# 切换到脚本目录
cd "$SCRIPT_DIR" || { echo "${LOG_PREFIX} 无法进入脚本目录，退出"; exit 1; }
echo "${LOG_PREFIX} 当前目录: $(pwd)"

# 设置日志文件目录
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "${LOG_DIR}" || { echo "${LOG_PREFIX} 无法创建日志目录 ${LOG_DIR}"; }

# 设置日志文件
LOG_FILE="${LOG_DIR}/sources_health_check_$(date +%Y%m%d_%H%M%S).log"
touch "$LOG_FILE" || { echo "${LOG_PREFIX} 无法创建日志文件 ${LOG_FILE}"; }
echo "${LOG_PREFIX} 日志文件: $LOG_FILE"

# 记录环境信息
echo "${LOG_PREFIX} 系统信息:" | tee -a "$LOG_FILE"
echo "${LOG_PREFIX} $(uname -a)" | tee -a "$LOG_FILE"

# 检查python虚拟环境
if [ -d "venv" ]; then
    echo "${LOG_PREFIX} 使用虚拟环境" | tee -a "$LOG_FILE"
    source venv/bin/activate
elif [ -d "../venv" ]; then
    echo "${LOG_PREFIX} 使用上级目录虚拟环境" | tee -a "$LOG_FILE"
    source ../venv/bin/activate
else
    echo "${LOG_PREFIX} 未找到虚拟环境，将使用系统Python" | tee -a "$LOG_FILE"
fi

# 确保依赖已安装
if [ -f "requirements.txt" ]; then
    echo "${LOG_PREFIX} 检查依赖是否已安装" | tee -a "$LOG_FILE"
    pip install -r requirements.txt >> "$LOG_FILE" 2>&1
fi

# 检查python版本
PYTHON_VERSION=$(python3 --version)
echo "${LOG_PREFIX} Python版本: ${PYTHON_VERSION}" | tee -a "$LOG_FILE"

# 先运行错误信息清理脚本
echo "${LOG_PREFIX} 开始执行错误信息清理脚本..." | tee -a "$LOG_FILE"
python update_cls_error_info.py >> "$LOG_FILE" 2>&1
ERROR_INFO_RESULT=$?

if [ $ERROR_INFO_RESULT -eq 0 ]; then
    echo "${LOG_PREFIX} 错误信息清理脚本执行成功" | tee -a "$LOG_FILE"
else
    echo "${LOG_PREFIX} 错误信息清理脚本执行失败，退出码: $ERROR_INFO_RESULT" | tee -a "$LOG_FILE"
    # 继续执行，不因为这个脚本失败而退出整个流程
fi

# 执行健康检查脚本
echo "${LOG_PREFIX} 开始执行数据源健康检查脚本..." | tee -a "$LOG_FILE"
python check_sources_health.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

# 检查执行结果
if [ $EXIT_CODE -eq 0 ]; then
    echo "${LOG_PREFIX} 数据源健康检查脚本执行成功" | tee -a "$LOG_FILE"
else
    echo "${LOG_PREFIX} 数据源健康检查脚本执行失败，退出码: $EXIT_CODE" | tee -a "$LOG_FILE"
fi

# 通过mail命令发送执行结果通知（如果安装了sendmail或类似软件）
if command -v mail &> /dev/null && [ -n "$ADMIN_EMAIL" ]; then
    SUBJECT="[HeatLink] 数据源健康检查报告 $(date +%Y-%m-%d)"
    if [ $EXIT_CODE -eq 0 ]; then
        echo "数据源健康检查成功完成，详情请查看日志: $LOG_FILE" | mail -s "$SUBJECT" $ADMIN_EMAIL
    else
        echo "数据源健康检查失败，请检查日志: $LOG_FILE" | mail -s "$SUBJECT [错误]" $ADMIN_EMAIL
    fi
    echo "${LOG_PREFIX} 已发送通知邮件到 $ADMIN_EMAIL" | tee -a "$LOG_FILE"
fi

# 清理旧日志文件（保留最近7天的）
echo "${LOG_PREFIX} 清理旧日志文件..." | tee -a "$LOG_FILE"
find "${LOG_DIR}" -name "sources_health_check_*.log" -type f -mtime +7 -delete

# 如果使用了虚拟环境，则退出
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
    echo "${LOG_PREFIX} 已退出虚拟环境" | tee -a "$LOG_FILE"
fi

echo "${LOG_PREFIX} 健康检查脚本执行完毕" | tee -a "$LOG_FILE"
exit $EXIT_CODE 