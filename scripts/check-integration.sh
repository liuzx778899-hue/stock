#!/bin/bash
# check-integration.sh — 查找待集成测试任务
# 第一行输出判定结果

TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

comm -23 <(git tag --list "round-*-review" | grep -v "fail" | sed 's/-review$//' | sort) <(git tag --list "round-*-itest" | sed 's/-itest.*$//' | sort) | while read round; do
  [ -n "$round" ] && echo "  [TODO] $round-review → 待集成测试" >> "$TMPFILE"
done

TASKS=$(grep -c "^  \[TODO\]" "$TMPFILE" 2>/dev/null || true)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待集成测试: $TASKS 个 — 必须立即开工 <<<"
  echo ""
  cat "$TMPFILE"
else
  echo ">>> 待集成测试: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
