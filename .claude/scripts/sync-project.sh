#!/bin/bash
# sync-project.sh — 同步提交到 GitHub Project 看板
# 使用 GitHub CLI 更新 Project item 状态

set -e

# GitHub CLI 路径
GH="/c/Program Files/GitHub CLI/gh.exe"

# 获取当前分支的最新提交信息
CURRENT_BRANCH=$(git branch --show-current)
COMMIT_MSG=$(git log -1 --pretty=%s)
COMMIT_HASH=$(git log -1 --pretty=%h)

# 解析 Issue 编号（如果有）
ISSUE_NUM=$(echo "$COMMIT_MSG" | grep -oE '#[0-9]+' | head -1 | tr -d '#')

if [ -z "$ISSUE_NUM" ]; then
    echo "未检测到 Issue 编号，跳过同步"
    exit 0
fi

echo "检测到 Issue #$ISSUE_NUM，开始同步..."

# 检查 gh 是否可用
if [ ! -f "$GH" ]; then
    echo "警告: GitHub CLI 未安装，无法同步 Project"
    exit 0
fi

# Project 配置（需要根据实际 Project ID 配置）
# PROJECT_NUMBER=1  # 替换为实际的 Project 编号

# 根据 commit 类型判断状态
STATUS="Todo"
if echo "$COMMIT_MSG" | grep -qiE "^feat|^fix"; then
    STATUS="In Progress"
elif echo "$COMMIT_MSG" | grep -qi "完成\|done\|完成"; then
    STATUS="Done"
fi

echo "提交: $COMMIT_HASH"
echo "分支: $CURRENT_BRANCH"
echo "Issue: #$ISSUE_NUM"
echo "状态: $STATUS"

# 实际同步需要 GitHub CLI 和 Project 访问权限
# 示例命令（需要配置 PROJECT_NUMBER）:
# "$GH" project item-edit --project-number $PROJECT_NUMBER --id ITEM_ID --field "Status" --value "$STATUS"

echo "同步完成提示: 请手动更新 GitHub Project #$ISSUE_NUM 状态为 $STATUS"
