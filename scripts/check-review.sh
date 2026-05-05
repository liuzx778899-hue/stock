#!/bin/bash
# check-review.sh — 查找待审查任务
# 最后一行 TASKS:N 决定是否开工

TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# round-*-dev 无对应 review 的
comm -23 <(git tag --list "round-*-dev" | sed 's/-dev$//' | sort) <(git tag --list "round-*-review*" | sed 's/-review.*$//' | sort) | while read round; do
  [ -n "$round" ] && echo "TODO: $round-dev → 待审查" >> "$TMPFILE"
done

# fix-BUG-* 无对应 review 的
comm -23 <(git tag --list "fix-BUG-*" | sed 's/fix-BUG-//' | sort -n) <(git tag --list "round-BUG*-review" | sed 's/round-BUG//;s/-review$//' | sort -n) | while read bug; do
  [ -n "$bug" ] && echo "TODO: BUG-$bug → 待审查" >> "$TMPFILE"
done

cat "$TMPFILE"
TASKS=$(grep -c "^TODO:" "$TMPFILE" 2>/dev/null || true)
TASKS=${TASKS:-0}
rm -f "$TMPFILE"

if [ "$TASKS" -gt 0 ]; then
  echo ""
  echo "待审查任务总数: $TASKS — 必须开工"
else
  echo ""
  echo "待审查任务总数: 0 — 确实无任务"
fi
