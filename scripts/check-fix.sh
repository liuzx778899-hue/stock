#!/bin/bash
# check-fix.sh — 只输出待修复 Bug
# 第一行判定，Agent 必须无条件服从

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# A. GitHub bug Issues 无 fix 分支的
if [ -f "$GH" ]; then
  "$GH" issue list --label bug --state open --json number,title --jq '.[] | "BUG-#\(.number) \(.title)"' 2>/dev/null | while read line; do
    num=$(echo "$line" | sed 's/^BUG-#\([0-9]*\).*/\1/')
    if git branch -r | grep -q "origin/fix/BUG-$num" 2>/dev/null; then continue; fi
    if git tag --list "fix-BUG-$num" | grep -q . 2>/dev/null; then continue; fi
    echo "$line (无分支)" >> "$TMPFILE"
  done
fi

# B. fix tag 无 review 的
for tag in $(git tag --list "fix-BUG-*"); do
  bug_id=$(echo $tag | sed 's/fix-BUG-/BUG/')
  if ! git tag --list "round-${bug_id}-review" | grep -q . 2>/dev/null; then
    echo "$tag (待审查)" >> "$TMPFILE"
  fi
done

TASKS=$(wc -l < "$TMPFILE" 2>/dev/null || echo 0)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待修复 Bug: $TASKS 个 — 必须立即开工 <<<"
  cat "$TMPFILE"
else
  echo ">>> 待修复 Bug: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
