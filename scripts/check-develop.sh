#!/bin/bash
# check-develop.sh — 只输出 develop1 的待办任务
# 使用 dispatch.sh 的 JSON 分派结果
# 第一行判定，Agent 必须无条件服从

TMPFILE=$(mktemp)

# 使用 dispatch.sh 的输出，只取 role="develop" 的任务（排除 develop2）
bash scripts/dispatch.sh 2>/dev/null | grep '"role":"develop"' | grep -v '"role":"develop2"' | while read line; do
  issue=$(echo "$line" | sed 's/.*"issue":\([0-9]*\).*/\1/')
  task=$(echo "$line" | sed 's/.*"task":"\([^"]*\)".*/\1/')
  echo "#$issue $task" >> "$TMPFILE"
done

TASKS=$(wc -l < "$TMPFILE" 2>/dev/null || echo 0)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待开发任务: $TASKS 个 — 必须立即开工 <<<"
  cat "$TMPFILE"
else
  echo ">>> 待开发任务: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
