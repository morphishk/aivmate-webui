#!/bin/bash

# 启动 OpenCode Web UI（后台，stdout/stderr 直接输出到容器日志）
opencode web --port 3000 --hostname 0.0.0.0 &

# 读取 config.json 中的日志配置（兼容旧版，默认值：logs/run.log）
CONFIG_FILE="/app/data/db/config.json"
if [ -f "$CONFIG_FILE" ]; then
    LOG_PATH=$(python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d.get('log_path','logs'))")
    LOG_NAME=$(python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d.get('log_name','run.log'))")
else
    LOG_PATH="logs"
    LOG_NAME="run.log"
fi

# 确保日志目录存在（相对 /app）
mkdir -p "/app/$LOG_PATH"
LOG_FILE="/app/$LOG_PATH/$LOG_NAME"

# 启动时清空旧日志（避免无限追加）
> "$LOG_FILE"

# 启动主程序，stdout+stderr 同时输出到终端和日志文件
exec /opt/venv/bin/python /app/main.py > >(tee -a "$LOG_FILE") 2>&1
