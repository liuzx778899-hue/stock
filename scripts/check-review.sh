#!/bin/bash
# check-review.sh — 只输出待审查任务
# 第一行判定，Agent 必须无条件服从

TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

comm -23 <(git tag --list "round-*-dev" | sed 's/-dev$//' | sort) <(git tag --list "round-*-review*" | sed 's/-review.*$//' | sort) | while read round; do
  [ -n "$round" ] && echo "$round-dev" >> "$TMPFILE"
done

comm -23 <(git tag --list "fix-BUG-*" | sed 's/fix-BUG-//' | sort -n) <(git tag --list "round-BUG*-review" | sed 's/round-BUG//;s/-review$//' | sort -n) | while read bug; do
  [ -n "$bug" ] && echo "BUG-$bug" >> "$TMPFILE"
done

# review-fail 提示 — 检查是否已有对应的 dev/fix tag（存在即视为已修复）
for tag in $(git tag --list "round-*-review-fail"); do
  round=$(echo $tag | sed 's/-review-fail$//')
  # 已有 dev tag → 已修复，不再提示
  if git tag --list "${round}-dev" | grep -q . 2>/dev/null; then
    continue
  fi
  # 已有 fix tag → 已修复，不再提示
  bug_id=$(echo "$round" | sed 's/round-//')
  if echo "$bug_id" | grep -q "^BUG"; then
    if git tag --list "fix-${bug_id}" | grep -q . 2>/dev/null; then
      continue
    fi
  fi
  echo "[FAIL] $tag → 等待 bugfixer 修复" >> "$TMPFILE"
done

TASKS=$(wc -l < "$TMPFILE" 2>/dev/null || echo 0)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待审查: $TASKS 个 — 必须立即开工 <<<"
  cat "$TMPFILE"
else
  echo ">>> 待审查: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
