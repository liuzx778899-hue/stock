#!/bin/bash
# check-review.sh — 查找待审查任务（test1 用）
# 输出：每行一个待审查轮次，无输出 = 无任务

git fetch origin --tags 2>/dev/null

echo "=== 待审查 round ==="
comm -23 <(git tag --list "round-*-dev" | sed 's/-dev$//' | sort) <(git tag --list "round-*-review*" | sed 's/-review.*$//' | sort)

echo "=== 待审查 BUG ==="
comm -23 <(git tag --list "fix-BUG-*" | sed 's/fix-BUG-//' | sort -n) <(git tag --list "round-BUG*-review" | sed 's/round-BUG//;s/-review$//' | sort -n)
