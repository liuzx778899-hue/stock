#!/bin/bash
# check-integration.sh — 查找待集成测试任务（integration 用）
# 输出：每行一个待测试轮次，无输出 = 无任务

git fetch origin --tags 2>/dev/null

echo "=== 待集成测试 ==="
comm -23 <(git tag --list "round-*-review" | grep -v "fail" | sed 's/-review$//' | sort) <(git tag --list "round-*-itest" | sed 's/-itest.*$//' | sort)
