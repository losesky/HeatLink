#!/bin/bash
# 清理Chrome进程的cron脚本
# 建议添加到crontab，例如：
# */30 * * * * /path/to/clean_chrome_cron.sh >> /path/to/chrome_cleanup.log 2>&1

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 设置日志文件
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/chrome_cleanup_$(date +%Y%m%d).log"

# 设置时间戳函数
timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

# 记录开始时间
echo "$(timestamp) - 开始Chrome进程清理" | tee -a "$LOG_FILE"

# 检查psutil模块是否安装
if python3 -c "import psutil" &>/dev/null; then
  echo "$(timestamp) - psutil模块已安装" | tee -a "$LOG_FILE"
else
  echo "$(timestamp) - psutil模块未安装，尝试安装..." | tee -a "$LOG_FILE"
  pip install psutil
  if [ $? -ne 0 ]; then
    echo "$(timestamp) - 错误：安装psutil失败，无法继续清理" | tee -a "$LOG_FILE"
    exit 1
  fi
fi

# 检查Python清理脚本是否存在
CLEANER_SCRIPT="$SCRIPT_DIR/backend/clean_chrome_processes.py"
if [ ! -f "$CLEANER_SCRIPT" ]; then
  # 尝试不同路径
  CLEANER_SCRIPT="$SCRIPT_DIR/clean_chrome_processes.py"
  if [ ! -f "$CLEANER_SCRIPT" ]; then
    echo "$(timestamp) - 错误：找不到Chrome清理脚本，将尝试使用系统命令清理" | tee -a "$LOG_FILE"
    
    # 使用系统命令清理Chrome进程
    echo "$(timestamp) - 使用系统命令清理Chrome相关进程" | tee -a "$LOG_FILE"
    CHROME_COUNT=$(ps -ef | grep -i chrome | grep -v grep | wc -l)
    DRIVER_COUNT=$(ps -ef | grep -i chromedriver | grep -v grep | wc -l)
    echo "$(timestamp) - 发现 $CHROME_COUNT 个Chrome进程和 $DRIVER_COUNT 个ChromeDriver进程" | tee -a "$LOG_FILE"
    
    # 杀死Chrome进程
    pkill -f chrome
    pkill -f chromedriver
    
    # 确保所有进程都已终止
    sleep 1
    pkill -9 -f chrome
    pkill -9 -f chromedriver
    
    REMAINING=$(ps -ef | grep -i chrome | grep -v grep | wc -l)
    echo "$(timestamp) - 清理完成，剩余 $REMAINING 个Chrome相关进程" | tee -a "$LOG_FILE"
    exit 0
  fi
fi

# 执行Python清理脚本
echo "$(timestamp) - 执行Chrome清理脚本: $CLEANER_SCRIPT" | tee -a "$LOG_FILE"
python3 "$CLEANER_SCRIPT" 2>&1 | tee -a "$LOG_FILE"

# 检查脚本执行结果
if [ ${PIPESTATUS[0]} -eq 0 ]; then
  echo "$(timestamp) - Chrome进程清理完成" | tee -a "$LOG_FILE"
else
  echo "$(timestamp) - Chrome进程清理失败，退出码: ${PIPESTATUS[0]}" | tee -a "$LOG_FILE"
fi

# 检查系统中剩余的Chrome进程数量
REMAINING_CHROME=$(ps -ef | grep -i chrome | grep -v grep | wc -l)
echo "$(timestamp) - 系统中剩余 $REMAINING_CHROME 个Chrome相关进程" | tee -a "$LOG_FILE"

# 输出分隔符，便于日志阅读
echo "--------------------------------------------------------" | tee -a "$LOG_FILE"

exit 0 