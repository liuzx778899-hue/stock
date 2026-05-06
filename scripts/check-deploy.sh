#!/bin/bash
# check-deploy.sh — 只输出待部署任务
# 第一行判定，Agent 必须无条件服从

GH="/c/Program Files/GitHub CLI/gh.exe"
TMPFILE=$(mktemp)

git fetch origin --tags 2>/dev/null

# A. ui tag 有但 deploy 无 → 待部署，同时找对应分支
comm -23 <(git tag --list "round-*-ui" | sed 's/^round-//;s/-ui$//' | sort) <(git tag --list "deploy-*" | sed 's/^deploy-//' | sort) | while read id; do
  [ -z "$id" ] && continue
  # 找对应分支名
  if echo "$id" | grep -q "^BUG"; then
    bug_num=$(echo "$id" | sed 's/^BUG//')
    branch="fix/BUG-${bug_num}"
  else
    round_num=$(echo "$id" | grep -oE '^[0-9]+')
    branch=$(git branch -r | grep "origin/feature/${round_num}-" | sed 's/.*origin\///' | head -1)
    [ -z "$branch" ] && branch="feature/${round_num}-t1"
  fi
  echo "$id BRANCH=$branch" >> "$TMPFILE"
done

# A2. itest 有但 ui 无 → 提示等待 puppeteer
comm -23 <(git tag --list "round-*-itest" | grep -v "fail" | sed 's/^round-//;s/-itest$//' | sort) <(git tag --list "round-*-ui" | sed 's/^round-//;s/-ui$//' | sort) | while read id; do
  [ -n "$id" ] && echo "[BLOCKED] $id (itest通过但缺UI验证, 等待puppeteer)" >> "$TMPFILE"
done

# B. master 有代码但 Issue 未关
if [ -f "$GH" ]; then
  "$GH" issue list --state open --json number,title --jq '.[] | "#\(.number) \(.title)"' 2>/dev/null | while read line; do
    num=$(echo "$line" | sed 's/^#\([0-9]*\).*/\1/')
    if git log origin/master --oneline --grep="#$num" 2>/dev/null | grep -q .; then
      echo "$line (代码已部署, 关Issue: gh issue close $num)" >> "$TMPFILE"
    fi
  done
fi

TASKS=$(grep -c "^[0-9]\|^BUG" "$TMPFILE" 2>/dev/null || true)
TASKS=${TASKS:-0}

if [ "$TASKS" -gt 0 ]; then
  echo ">>> 待部署: $TASKS 个 — 必须立即开工 <<<"
  cat "$TMPFILE"
else
  echo ">>> 待部署: 0 个，确实无任务 <<<"
fi

rm -f "$TMPFILE"
