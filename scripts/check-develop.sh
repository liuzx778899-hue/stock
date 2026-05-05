#!/bin/bash
# check-develop.sh — 查找待开发任务（develop1 / develop2 共用）

GH="/c/Program Files/GitHub CLI/gh.exe"

git fetch origin --tags 2>/dev/null

# A. GitHub enhancement Issues
echo "=== enhancement Issues ==="
if [ -f "$GH" ]; then
  "$GH" issue list --label enhancement --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null | while read line; do
    num=$(echo "$line" | sed 's/^#\([0-9]*\).*/\1/')
    # 检查是否有未合并分支的 commit 引用了 fixes #N
    found=0
    for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
      if ! git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then
        if git log origin/master..origin/$b --oneline --grep="fixes #$num" 2>/dev/null | grep -q .; then
          echo "🔧 $line → $b"
          found=1
          break
        fi
      fi
    done
    if [ "$found" -eq 0 ]; then
      echo "🆕 $line (无分支)"
    fi
  done
else
  echo "(gh CLI 未找到)"
fi

# B. feature 分支逐条检查
echo "=== feature 分支状态 ==="
for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
  if git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then
    continue
  fi
  round=$(echo "$b" | grep -oE '[0-9]+' | head -1)
  if [ -z "$round" ]; then continue; fi

  # 检查该轮次的 tag（不管 tag 是否在 HEAD）
  dev_tag=$(git tag --list "round-${round}-dev" 2>/dev/null)
  review_tag=$(git tag --list "round-${round}-review" 2>/dev/null)
  itest_tag=$(git tag --list "round-${round}-itest" 2>/dev/null)
  count=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo 0)

  if [ -n "$itest_tag" ]; then
    echo "✅ $b → $itest_tag (集成测试通过)"
  elif [ -n "$review_tag" ]; then
    echo "✅ $b → $review_tag (待集成测试)"
  elif [ -n "$dev_tag" ]; then
    echo "✅ $b → $dev_tag (待审查)"
  elif [ "$count" -gt 0 ]; then
    echo "🔧 $b ($count commits, 无 dev tag — 待完成)"
  else
    echo "🆕 $b (无 commits — 新任务)"
  fi
done
