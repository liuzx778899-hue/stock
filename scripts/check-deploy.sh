#!/bin/bash
# check-deploy.sh — 查找待部署 + 代码已合但 Issue 未关的任务
# 第一行输出判定结果

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# A. itest 有但 deploy 无 → 待部署
comm -23 <(git tag --list "round-*-itest" | grep -v "fail" | sed 's/^round-//;s/-itest$//' | sort) <(git tag --list "deploy-*" | sed 's/^deploy-//' | sort) | while read id; do
  [ -n "$id" ] && echo "  [TODO] $id → 待部署" >> "$TMPFILE"
done

# B. 代码已在 master 但 Issue 仍 open → 需关 Issue
if [ -f "$GH" ]; then
  "$GH" issue list --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null | while read line; do
    num=$(echo "$line" | sed 's/^#\([0-9]*\).*/\1/')
    # 检查 master 是否有提交引用该 Issue
    if git log origin/master --oneline --grep="#$num" 2>/dev/null | grep -q .; then
      echo "  [TODO] $line → master 已有代码但 Issue 未关, 执行 gh issue close $num" >> "$TMPFILE"
    fi
  done
fi

TASKS=$(grep -c "^  \[TODO\]" "$TMPFILE" 2>/dev/null || true)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待部署任务: $TASKS 个 — 必须立即开工 <<<"
  echo ""
  cat "$TMPFILE"
else
  echo ">>> 待部署任务: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
