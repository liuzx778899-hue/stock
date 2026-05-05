#!/bin/bash
# check-integration.sh — 查找待集成测试任务
# 最后一行 TASKS:N 决定是否开工

TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

comm -23 <(git tag --list "round-*-review" | grep -v "fail" | sed 's/-review$//' | sort) <(git tag --list "round-*-itest" | sed 's/-itest.*$//' | sort) | while read round; do
  [ -n "$round" ] && echo "TODO: $round-review → 待集成测试" >> "$TMPFILE"
done

cat "$TMPFILE"
TASKS=$(grep -c "^TODO:" "$TMPFILE" 2>/dev/null || echo 0)
rm -f "$TMPFILE"

if [ "$TASKS" -gt 0 ]; then
  echo ""
  echo "待集成测试总数: $TASKS — 必须开工"
else
  echo ""
  echo "待集成测试总数: 0 — 确实无任务"
fi
