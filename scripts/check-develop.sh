#!/bin/bash
# check-develop.sh — 查找待开发任务
# 第一行输出判定结果，Agent 必须以此为准

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)
ISSUES_FILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# A. GitHub enhancement Issues 无对应提交的
if [ -f "$GH" ]; then
  "$GH" issue list --label enhancement --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null > "$ISSUES_FILE"
  while read line; do
    num=$(echo "$line" | sed 's/^#\([0-9]*\).*/\1/')
    if git log --all --oneline --grep="#$num" 2>/dev/null | grep -q .; then
      echo "  [DONE] $line" >> "$TMPFILE"
    else
      echo "  [TODO] $line" >> "$TMPFILE"
    fi
  done < "$ISSUES_FILE"
  rm -f "$ISSUES_FILE"
fi

# B. feature 分支逐条检查
for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
  if git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then
    continue
  fi
  round_num=$(echo "$b" | sed 's/feature\/\([0-9]*\).*/\1/')
  tag=$(git tag --list "round-${round_num}-dev" 2>/dev/null | head -1)
  count=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo 0)
  if [ -n "$tag" ]; then
    echo "  [DONE] $b -> $tag" >> "$TMPFILE"
  elif [ "$count" -gt 0 ]; then
    echo "  [TODO] $b ($count commits, 缺 dev tag)" >> "$TMPFILE"
  else
    echo "  [TODO] $b (空分支)" >> "$TMPFILE"
  fi
done

# 先输出判定结果，再输出详情
TASKS=$(grep -c "^  \[TODO\]" "$TMPFILE" 2>/dev/null || true)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待开发任务: $TASKS 个 — 必须立即开工 <<<"
  echo ""
  cat "$TMPFILE"
else
  echo ">>> 待开发任务: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
