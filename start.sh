#!/bin/bash
# A股数据采集系统 - 启动脚本
# 用法: ./start.sh [all|backend|frontend] [DB_PASSWORD]

set -e

MODE="${1:-all}"
DB_PASSWORD="${2:-}"

echo "========================================"
echo "  A股数据采集系统启动脚本"
echo "========================================"
echo ""

# 设置数据库密码
if [ -n "$DB_PASSWORD" ]; then
    export DB_PASSWORD="$DB_PASSWORD"
    echo "[OK] 数据库密码已设置"
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 Python
if ! command -v python &> /dev/null; then
    echo "[ERROR] 未找到 Python，请先安装"
    exit 1
fi
echo "[OK] Python 已安装"

# 检查 Node.js（仅前端模式需要）
if [ "$MODE" = "frontend" ] || [ "$MODE" = "all" ]; then
    if ! command -v npm &> /dev/null; then
        echo "[ERROR] 未找到 Node.js/npm，请先安装"
        exit 1
    fi
    echo "[OK] Node.js/npm 已安装"
fi

# 检查依赖是否已安装
if [ ! -f "requirements.txt" ]; then
    echo "[ERROR] 未找到 requirements.txt"
    exit 1
fi

echo ""
echo "启动模式: $MODE"
echo ""

# 清理函数
cleanup() {
    echo ""
    echo "正在停止服务..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo "[OK] 服务已停止"
    exit 0
}

trap cleanup SIGINT SIGTERM

case "$MODE" in
    backend)
        echo "启动后端 API..."
        python web_app.py
        ;;

    frontend)
        echo "启动前端开发服务器..."
        cd frontend
        npm run dev
        ;;

    all)
        echo "同时启动后端 + 前端..."
        echo ""

        # 启动后端（后台）
        echo "[1] 启动后端 API (http://localhost:8000)"
        python web_app.py &
        BACKEND_PID=$!

        # 等待后端启动
        sleep 3

        # 启动前端（后台）
        echo "[2] 启动前端开发服务器 (http://localhost:3000)"
        cd frontend
        npm run dev &
        FRONTEND_PID=$!
        cd ..

        echo ""
        echo "========================================"
        echo "  服务已启动!"
        echo "========================================"
        echo ""
        echo "  前端: http://localhost:3000"
        echo "  后端: http://localhost:8000"
        echo "  API文档: http://localhost:8000/docs"
        echo ""
        echo "  按 Ctrl+C 停止所有服务"
        echo ""

        # 等待任一进程结束
        wait
        ;;

    *)
        echo "[ERROR] 无效的模式: $MODE"
        echo "用法: ./start.sh [all|backend|frontend] [DB_PASSWORD]"
        exit 1
        ;;
esac
