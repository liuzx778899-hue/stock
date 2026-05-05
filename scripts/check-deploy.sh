#!/bin/bash
# check-deploy.sh — 查找待部署任务
# 最后一行 TASKS:N 决定是否开工

TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

comm -23 <(git tag --list "round-*-itest" | grep -v "fail" | sed 's/^round-//;s/-itest$//' | sort) <(git tag --list "deploy-*" | sed 's/^deploy-//' | sort) | while read id; do
  [ -n "$id" ] && echo "TODO: $id → 待部署" >> "$TMPFILE"
done

cat "$TMPFILE"
TASKS=$(grep -c "^TODO:" "$TMPFILE" 2>/dev/null || true)
TASKS=${TASKS:-0}
rm -f "$TMPFILE"

if [ "$TASKS" -gt 0 ]; then
  echo ""
  echo "待部署任务总数: $TASKS — 必须开工"
else
  echo ""
  echo "待部署任务总数: 0 — 确实无任务"
fi
