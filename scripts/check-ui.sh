#!/bin/bash
# check-ui.sh — 查找待 UI 验证任务
# 第一行判定，Agent 必须无条件服从

TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

comm -23 <(git tag --list "round-*-itest" | grep -v "fail" | sed 's/-itest$//' | sort) <(git tag --list "round-*-ui" | sed 's/-ui$//' | sort) | while read round; do
  [ -n "$round" ] && echo "$round" >> "$TMPFILE"
done

TASKS=$(wc -l < "$TMPFILE" 2>/dev/null || echo 0)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待 UI 验证: $TASKS 个 — 必须立即开工 <<<"
  cat "$TMPFILE"
else
  echo ">>> 待 UI 验证: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
