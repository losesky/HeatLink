#!/bin/bash

# 日志颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}     日志文件清理和压缩工具     ${NC}"
echo -e "${BLUE}=====================================${NC}"

# 获取当前目录
CURRENT_DIR=$(pwd)
echo -e "${GREEN}当前目录: ${CURRENT_DIR}${NC}"

# 日志目录
LOG_DIR="logs"
if [ ! -d "$LOG_DIR" ]; then
    echo -e "${YELLOW}创建日志目录 ${LOG_DIR}${NC}"
    mkdir -p "$LOG_DIR"
fi

# 存档目录
ARCHIVE_DIR="${LOG_DIR}/archive"
if [ ! -d "$ARCHIVE_DIR" ]; then
    echo -e "${YELLOW}创建日志存档目录 ${ARCHIVE_DIR}${NC}"
    mkdir -p "$ARCHIVE_DIR"
fi

# 日期标记
DATE_TAG=$(date +%Y%m%d)

# 清理函数
clean_logs() {
    echo -e "${GREEN}开始清理日志文件...${NC}"
    
    # 压缩超过7天的日志文件
    echo -e "${YELLOW}查找并压缩超过7天的日志文件...${NC}"
    find "$LOG_DIR" -name "*.log" -type f -mtime +7 | while read -r log_file; do
        filename=$(basename "$log_file")
        echo -e "压缩: $filename"
        gzip -c "$log_file" > "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.gz"
        if [ $? -eq 0 ]; then
            echo -e "删除原始文件: $log_file"
            rm "$log_file"
        else
            echo -e "${RED}压缩失败，保留原始文件: $log_file${NC}"
        fi
    done
    
    # 删除超过30天的压缩日志
    echo -e "${YELLOW}删除超过30天的压缩日志...${NC}"
    find "$ARCHIVE_DIR" -name "*.gz" -type f -mtime +30 | while read -r old_log; do
        echo -e "删除旧压缩日志: $old_log"
        rm "$old_log"
    done
    
    # 压缩当前大于50MB的日志文件但不删除
    echo -e "${YELLOW}查找并压缩当前大于50MB的日志文件...${NC}"
    find "$LOG_DIR" -name "*.log" -type f -size +50M | while read -r large_log; do
        filename=$(basename "$large_log")
        echo -e "压缩大文件: $filename"
        cp "$large_log" "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.copy"
        truncate -s 0 "$large_log"
        echo -e "[日志已于 $(date) 被清空以节省空间，完整日志已存档]" > "$large_log"
        gzip -c "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.copy" > "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.gz"
        rm "${ARCHIVE_DIR}/${filename}.${DATE_TAG}.copy"
    done
    
    # 显示当前日志使用情况
    echo -e "${GREEN}当前日志使用情况:${NC}"
    du -h "$LOG_DIR" | sort -hr
    
    echo -e "${GREEN}日志清理完成!${NC}"
}

# 执行清理
clean_logs

echo -e "${BLUE}=====================================${NC}"
echo -e "${GREEN}所有操作已完成!${NC}"
echo -e "${YELLOW}提示: 可以将此脚本添加到crontab以定期自动运行${NC}"
echo -e "${YELLOW}例如: 0 0 * * * $(readlink -f "$0") > /dev/null 2>&1${NC}"
echo -e "${BLUE}=====================================${NC}" 