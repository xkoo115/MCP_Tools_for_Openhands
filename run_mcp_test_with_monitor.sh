#!/bin/bash-59-generic x86_64)

# 运行监控脚本
MAIN_SCRIPT="run_1_eval".com
LOG_FILE="nohup_logs/run_mcp_test_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="/tmp/run_mcp_test.pid"

echo "=== 启动脚本监控 ==="
echo "主脚本: $MAIN_SCRIPT"
echo "日志文件: $LOG_FILE"
echo "PID文件: $PID_FILE"
echo "启动时间: $(date)"

# 检查脚本是否存在
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "错误: 脚本 $MAIN_SCRIPT 不存在!"
    exit 1
fi

# 使用nohup启动
nohup bash "$MAIN_SCRIPT" \
  --agent-llm-config llm.deepseek_v32 \
  --env-llm-config llm.qwen_plus \
  --outputs-path outputs_mcp_test \
  --task-name hr-green-card-consultation \
  --version 1.0.0 > "$LOG_FILE" 2>&1 &

# 保存PID
PID=$!
echo $PID > "$PID_FILE"

echo "脚本已启动，PID: $PID"
echo "使用以下命令查看实时日志:"
echo "  tail -f $LOG_FILE"
echo "使用以下命令停止进程:"
echo "  sudo kill $PID"
echo ""
echo "进程状态:"
ps -p $PID > /dev/null 2>&1 && echo "✅ 运行中
" || echo "❌ 已停止"