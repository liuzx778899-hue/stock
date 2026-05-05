#!/bin/bash
# check-develop.sh — 查找待开发任务
# 最后一行 TASKS:N 决定是否开工

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# A. GitHub enhancement Issues 无对应提交的
if [ -f "$GH" ]; then
  "$GH" issue list --label enhancement --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null | while read line; do
    num=$(echo "$line" | sed 's/^#\([0-9]*\).*/\1/')
    # 检查所有提交是否引用该 Issue
    if git log --all --oneline --grep="#$num" 2>/dev/null | grep -q .; then
      echo "OK: $line -> 已有提交引用" >> "$TMPFILE"
    else
      echo "TODO: $line -> 建 feature 分支开始开发" >> "$TMPFILE"
    fi
  done
fi

# B. feature 分支逐条检查
for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
  if git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then
    continue
  fi
  # 从分支名提取轮次号，直接查对应 dev tag
  round_num=$(echo "$b" | sed 's/feature\/\([0-9]*\).*/\1/')
  tag=$(git tag --list "round-${round_num}-dev" 2>/dev/null | head -1)
  count=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo 0)
  if [ -n "$tag" ]; then
    echo "OK: $b -> $tag" >> "$TMPFILE"
  elif [ "$count" -gt 0 ]; then
    echo "TODO: $b -> $count commits 未打 dev tag, checkout 继续开发并打 tag" >> "$TMPFILE"
  else
    echo "TODO: $b -> 空分支, checkout 开始开发" >> "$TMPFILE"
  fi
done

cat "$TMPFILE"
TASKS=$(grep -c "^TODO:" "$TMPFILE" 2>/dev/null || echo 0)
rm -f "$TMPFILE"

if [ "$TASKS" -gt 0 ]; then
  echo ""
  echo "============================================"
  echo "待开发任务总数: $TASKS"
  echo "指令: 选第一个 TODO 任务开始开发，禁止输出'无任务'"
  echo "============================================"
else
  echo ""
  echo "待开发任务总数: 0 — 确实无任务"
fi