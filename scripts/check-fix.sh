#!/bin/bash
# check-fix.sh — 查找待修复 Bug
# 最后一行 TASKS:N 决定是否开工

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# A. GitHub bug Issues
if [ -f "$GH" ]; then
  "$GH" issue list --label bug --state open --json number,title --jq '.[] | "BUG-#\(.number) \(.title)"' 2>/dev/null | while read line; do
    num=$(echo "$line" | sed 's/^BUG-#\([0-9]*\).*/\1/')
    if git branch -r | grep -q "origin/fix/BUG-$num" 2>/dev/null; then
      echo "OK: $line (已有 fix 分支)" >> "$TMPFILE"
    elif git tag --list "fix-BUG-$num" | grep -q . 2>/dev/null; then
      echo "OK: $line (已有 fix tag)" >> "$TMPFILE"
    else
      echo "TODO: $line → 建 fix/BUG-$num 分支开始修复" >> "$TMPFILE"
    fi
  done
fi

# B. fix 分支无 review 的
for tag in $(git tag --list "fix-BUG-*"); do
  bug_id=$(echo $tag | sed 's/fix-BUG-/BUG/')
  if ! git tag --list "round-${bug_id}-review" | grep -q . 2>/dev/null; then
    echo "TODO: $tag → 修复中，待审查" >> "$TMPFILE"
  fi
done

cat "$TMPFILE"
TASKS=$(grep -c "^TODO:" "$TMPFILE" 2>/dev/null || echo 0)
rm -f "$TMPFILE"

if [ "$TASKS" -gt 0 ]; then
  echo ""
  echo "待修复 Bug 总数: $TASKS — 必须开工"
else
  echo ""
  echo "待修复 Bug 总数: 0 — 确实无任务"
fi
