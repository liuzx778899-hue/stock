#!/bin/bash
# check-develop.sh — 只输出真正需要写代码的任务
# 排除：代码已在 master、已有 dev tag、PM 配置类任务
# 第一行判定，Agent 必须无条件服从

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)
ISSUES_FILE=$(mktemp)

git fetch origin --tags 2>/dev/null

if [ -f "$GH" ]; then
  "$GH" issue list --label enhancement --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null > "$ISSUES_FILE"
  while read line; do
    num=$(echo "$line" | sed 's/^#\([0-9]*\).*/\1/')

    # 排除：代码已在 master（交给 deploy 关 Issue）
    if git log origin/master --oneline --grep="#$num" 2>/dev/null | grep -q .; then
      continue
    fi

    # 排除：已有 feature 分支且打了 dev tag（已过开发阶段）
    has_dev_tag=0
    for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
      round_num=$(echo "$b" | sed 's/feature\/\([0-9]*\).*/\1/')
      tag=$(git tag --list "round-${round_num}-dev" 2>/dev/null | head -1)
      if [ -n "$tag" ]; then
        # 检查该分支的 commits 是否引用了该 Issue
        if git log origin/master..origin/$b --oneline --grep="#$num" 2>/dev/null | grep -q .; then
          has_dev_tag=1; break
        fi
      fi
    done
    [ "$has_dev_tag" -eq 1 ] && continue

    # 这个 Issue 真的需要从零开始开发
    echo "$line" >> "$TMPFILE"
  done < "$ISSUES_FILE"
  rm -f "$ISSUES_FILE"
fi

# B. 未合并的 feature 分支，无 dev tag 的
for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
  if git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then continue; fi
  round_num=$(echo "$b" | sed 's/feature\/\([0-9]*\).*/\1/')
  tag=$(git tag --list "round-${round_num}-dev" 2>/dev/null | head -1)
  [ -n "$tag" ] && continue
  count=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo 0)
  [ "$count" -eq 0 ] && continue
  echo "$b ($count commits, 缺 dev tag)" >> "$TMPFILE"
done

TASKS=$(wc -l < "$TMPFILE" 2>/dev/null || echo 0)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待开发任务: $TASKS 个 — 必须立即开工 <<<"
  cat "$TMPFILE"
else
  echo ">>> 待开发任务: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
