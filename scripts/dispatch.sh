#!/bin/bash
# dispatch.sh — 输出所有待办任务的 JSON，一行一个
# 用法: bash scripts/dispatch.sh

GH="/c/Program Files/GitHub CLI/gh.exe"
git fetch origin --force --tags --prune 2>/dev/null

# 辅助函数：该轮次是否已部署
is_deployed() {
  local round="$1"
  local deploy_id=$(echo "$round" | sed 's/^round-//')
  git tag --list "deploy-${deploy_id}" | grep -q . 2>/dev/null
}

# ===== bugfixer: 新 bug Issues =====
if [ -f "$GH" ]; then
  "$GH" issue list --label bug --state open --json number,title --jq '.[] | "\(.number)\t\(.title)"' 2>/dev/null | while IFS=$'\t' read num title; do
    if git branch -r | grep -q "origin/fix/BUG-$num" 2>/dev/null; then continue; fi
    if git tag --list "fix-BUG-$num" | grep -q . 2>/dev/null; then continue; fi
    echo "{\"role\":\"bugfixer\",\"issue\":$num,\"task\":\"$title\",\"branch\":null,\"reason\":\"新bug\"}"
  done
fi

# ===== bugfixer: review-fail 打回 =====
for tag in $(git tag --list "round-*-review-fail"); do
  round=$(echo $tag | sed 's/-review-fail$//')
  is_deployed "$round" && continue
  if git tag --list "${round}-dev" | grep -q . 2>/dev/null; then continue; fi
  if echo "$round" | grep -q "^round-BUG"; then
    num=$(echo "$round" | sed 's/round-BUG//')
    if git tag --list "fix-BUG-$num" | grep -q . 2>/dev/null; then continue; fi
    echo "{\"role\":\"bugfixer\",\"issue\":$num,\"task\":\"review-fail修复\",\"branch\":\"fix/BUG-$num\",\"reason\":\"review-fail打回\"}"
  fi
done

# ===== test1: dev tag 待审查 =====
for tag in $(git tag --list "round-*-dev"); do
  round=$(echo $tag | sed 's/-dev$//')
  is_deployed "$round" && continue
  if git tag --list "round-${round}-review*" | grep -q . 2>/dev/null; then continue; fi
  num=$(echo "$round" | grep -oE '[0-9]+' | head -1)
  [ -z "$num" ] && continue
  echo "{\"role\":\"test1\",\"issue\":$num,\"task\":\"审查 $tag\",\"branch\":\"feature/${num}-t1\",\"reason\":\"dev完成\"}"
done

# ===== test1: fix tag 待审查 =====
for tag in $(git tag --list "fix-BUG-*"); do
  bug_id=$(echo $tag | sed 's/fix-BUG-/BUG/')
  is_deployed "round-$bug_id" && continue
  if git tag --list "round-${bug_id}-review" | grep -q . 2>/dev/null; then continue; fi
  num=$(echo "$bug_id" | sed 's/^BUG//')
  echo "{\"role\":\"test1\",\"issue\":$num,\"task\":\"审查 $tag\",\"branch\":\"fix/BUG-$num\",\"reason\":\"fix完成\"}"
done

# ===== integration: review 待测试 =====
for tag in $(git tag --list "round-*-review" | grep -v "fail"); do
  round=$(echo $tag | sed 's/-review$//')
  is_deployed "$round" && continue
  if git tag --list "round-${round}-itest" | grep -q . 2>/dev/null; then continue; fi
  num=$(echo "$round" | grep -oE '[0-9]+' | head -1)
  [ -z "$num" ] && continue
  echo "{\"role\":\"integration\",\"issue\":$num,\"task\":\"集成测试 $round\",\"branch\":null,\"reason\":\"review通过\"}"
done

# ===== puppeteer: itest 待 UI =====
for tag in $(git tag --list "round-*-itest" | grep -v "fail"); do
  round=$(echo $tag | sed 's/-itest$//')
  is_deployed "$round" && continue
  if git tag --list "round-${round}-ui" | grep -q . 2>/dev/null; then continue; fi
  num=$(echo "$round" | grep -oE '[0-9]+' | head -1)
  [ -z "$num" ] && continue
  echo "{\"role\":\"puppeteer\",\"issue\":$num,\"task\":\"UI验证 $round\",\"branch\":null,\"reason\":\"itest通过\"}"
done

# ===== deploy: ui 待部署 =====
for tag in $(git tag --list "round-*-ui"); do
  round=$(echo $tag | sed 's/-ui$//')
  deploy_id=$(echo "$round" | sed 's/^round-//')
  if git tag --list "deploy-${deploy_id}" | grep -q . 2>/dev/null; then continue; fi
  num=$(echo "$round" | grep -oE '[0-9]+' | head -1)
  [ -z "$num" ] && continue
  if echo "$deploy_id" | grep -q "^BUG"; then
    bug_num=$(echo "$deploy_id" | sed 's/^BUG//')
    branch="fix/BUG-${bug_num}"
  else
    branch=$(git branch -r | grep "origin/feature/${num}-" | sed 's/.*origin\///' | head -1)
    [ -z "$branch" ] && branch="feature/${num}-t1"
  fi
  echo "{\"role\":\"deploy\",\"issue\":$num,\"task\":\"部署 $deploy_id\",\"branch\":\"$branch\",\"reason\":\"ui通过\"}"
done

# ===== develop: 新 enhancement =====
if [ -f "$GH" ]; then
  "$GH" issue list --label enhancement --state open --json number,title --jq '.[] | "\(.number)\t\(.title)"' 2>/dev/null | while IFS=$'\t' read num title; do
    if git log --all --oneline --grep="#$num" 2>/dev/null | grep -q .; then continue; fi
    # 根据 Issue 编号判断分配给 develop1 还是 develop2
    # develop2: Provider实现/API端点/前端 (Issue #147, #150 等)
    case $num in
      147|150) echo "{\"role\":\"develop2\",\"issue\":$num,\"task\":\"$title\",\"branch\":null,\"reason\":\"新enhancement\"}" ;;
      *) echo "{\"role\":\"develop\",\"issue\":$num,\"task\":\"$title\",\"branch\":null,\"reason\":\"新enhancement\"}" ;;
    esac
  done
fi

# ===== develop: feature 分支无 dev tag =====
for b in $(git branch -r | grep 'origin/feature/' | sed 's/.*origin\///'); do
  if git merge-base --is-ancestor origin/$b origin/master 2>/dev/null; then continue; fi
  round_num=$(echo "$b" | sed 's/feature\/\([0-9]*\).*/\1/')
  [ -z "$round_num" ] && continue
  is_deployed "round-$round_num" && continue
  if git tag --list "round-${round_num}-dev" | grep -q . 2>/dev/null; then continue; fi
  count=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo 0)
  [ "$count" -eq 0 ] && continue
  echo "{\"role\":\"develop\",\"issue\":$round_num,\"task\":\"继续开发 $b\",\"branch\":\"$b\",\"reason\":\"$count commits缺dev tag\"}"
done
