#!/bin/bash
# 安装 Git hooks 到 .git/hooks/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GIT_HOOKS_DIR="$(git rev-parse --git-dir)/hooks"

echo "安装 Git hooks..."

# 复制 hooks
cp "$SCRIPT_DIR/hooks/post-commit" "$GIT_HOOKS_DIR/"
cp "$SCRIPT_DIR/hooks/pre-push" "$GIT_HOOKS_DIR/"
cp "$SCRIPT_DIR/hooks/commit-msg" "$GIT_HOOKS_DIR/"

# 设置可执行权限
chmod +x "$GIT_HOOKS_DIR/post-commit"
chmod +x "$GIT_HOOKS_DIR/pre-push"
chmod +x "$GIT_HOOKS_DIR/commit-msg"

echo "✅ Git hooks 已安装:"
echo "   - post-commit: 解析任务编号 → 更新 agent-tasks.md"
echo "   - pre-push: 运行 pytest → 测试失败阻止推送"
echo "   - commit-msg: 验证 commit 格式"
