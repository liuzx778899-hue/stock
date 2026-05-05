#!/bin/bash
# check-develop.sh — 只输出待开发任务，不输出已完成的
# 第一行是判定，Agent 必须无条件服从

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)
ISSUES_FILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# A. enhancement Issues 无提交引用的
if [ -f "$GH" ]; then
  "$GH" issue list --label enhancement --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null > "$ISSUES_FILE"
  while read line; do
    num=$(echo "$line" | sed 's/^#\([0-9]*\).*/\1/')
    if ! git log --all --oneline --grep="#$num" 2>/dev/null | grep -q .; then
      echo "$line" >> "$TMPFILE"
    fi
  done < "$ISSUES_FILE"
  rm -f "$ISSUES_FILE"
fi

# B. 未合并 feature 分支无 dev tag 的
for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
  if git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then
    continue
  fi
  round_num=$(echo "$b" | sed 's/feature\/\([0-9]*\).*/\1/')
  tag=$(git tag --list "round-${round_num}-dev" 2>/dev/null | head -1)
  [ -n "$tag" ] && continue  # 已有 dev tag，跳过
  count=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo 0)
  if [ "$count" -gt 0 ]; then
    echo "$b ($count commits, 缺 dev tag)" >> "$TMPFILE"
  else
    echo "$b (空分支)" >> "$TMPFILE"
  fi
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
