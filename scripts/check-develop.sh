#!/bin/bash
# check-develop.sh — 查找待开发任务（develop1 / develop2 共用）
# 输出：每行一个待开发任务，无输出 = 无任务

git fetch origin --tags 2>/dev/null

echo "=== 未开始的 enhancement Issues ==="
gh issue list --label enhancement --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null

echo "=== feature 分支状态 ==="
for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
  if git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then
    continue  # 已合并，跳过
  fi
  # 找分支自身 commits 上的 dev tag
  tag=$(git tag --points-at $(git rev-list origin/master..origin/$b 2>/dev/null) --list "round-*-dev" 2>/dev/null | head -1)
  count=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo 0)
  if [ -n "$tag" ]; then
    echo "✅ $b → $tag ($count commits, 已完成)"
  elif [ "$count" -gt 0 ]; then
    echo "🔧 $b ($count commits, 无 dev tag — 待完成)"
  else
    echo "🆕 $b (无 commits — 新任务)"
  fi
done
