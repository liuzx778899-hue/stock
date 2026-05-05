#!/bin/bash
# check-fix.sh — 查找待修复 Bug（bugfixer 用）
# 输出：每行一个待修复 Bug，无输出 = 无任务

git fetch origin --tags 2>/dev/null

echo "=== 待修复 Bug Issues ==="
gh issue list --label bug --state open --json number,title --jq '.[] | "BUG-#\(.number) \(.title)"' 2>/dev/null

echo "=== fix 分支状态 ==="
for tag in $(git tag --list "fix-BUG-*"); do
  bug_id=$(echo $tag | sed 's/fix-BUG-/BUG/')
  if ! git tag --list "round-${bug_id}-review" | grep -q . 2>/dev/null; then
    echo "🔧 $tag → 修复中，待审查"
  fi
done
