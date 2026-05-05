#!/bin/bash
# check-fix.sh — 查找待修复 Bug（bugfixer 用）

GH="/c/Program Files/GitHub CLI/gh.exe"

git fetch origin --tags 2>/dev/null

# A. GitHub bug Issues
echo "=== 待修复 Bug Issues ==="
if [ -f "$GH" ]; then
  "$GH" issue list --label bug --state open --json number,title --jq '.[] | "BUG-#\(.number) \(.title)"' 2>/dev/null | while read line; do
    num=$(echo "$line" | sed 's/^BUG-#\([0-9]*\).*/\1/')
    # 检查是否有 fix 分支或 fix tag
    if git branch -r | grep -q "origin/fix/BUG-$num" 2>/dev/null; then
      echo "🔧 $line (已有 fix 分支)"
    elif git tag --list "fix-BUG-$num" | grep -q . 2>/dev/null; then
      echo "🔧 $line (已有 fix tag)"
    else
      echo "🆕 $line (无分支 — 待领取)"
    fi
  done
else
  echo "(gh CLI 未找到)"
fi

# B. fix 分支未审查的
echo "=== fix 分支待审查 ==="
for tag in $(git tag --list "fix-BUG-*"); do
  bug_id=$(echo $tag | sed 's/fix-BUG-/BUG/')
  if ! git tag --list "round-${bug_id}-review" | grep -q . 2>/dev/null; then
    echo "🔧 $tag → 修复中，待审查"
  fi
done
