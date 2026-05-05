#!/bin/bash
# check-deploy.sh — 查找待部署任务（deploy 用）
# 输出：每行一个待部署轮次，无输出 = 无任务

git fetch origin --tags 2>/dev/null

echo "=== 待部署（有 itest 无 deploy tag）==="
comm -23 <(git tag --list "round-*-itest" | grep -v "fail" | sed 's/-itest$//' | sort) <(git tag --list "deploy-*" | sed 's/deploy-//' | sort)
