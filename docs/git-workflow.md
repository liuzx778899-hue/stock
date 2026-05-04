# Git 驱动开发流程

## Issue 分诊（PM 统一管理）

**所有 Issue 由 PM 统一创建和打标签。**

```
有人发现问题/想法
      ↓
   告诉 PM
      ↓
  PM 判断类型：
  ├── 代码缺陷/崩溃 → --label bug → bugfixer 修复
  ├── 新功能/改进   → --label enhancement → 建需求文档 → develop 开发
  └── 拿不准/需讨论 → --label question → 讨论后转标签
```

| 标签 | 含义 | 谁来修 |
|------|------|--------|
| `bug` | 代码缺陷 | bugfixer |
| `enhancement` | 功能需求/改进 | develop |
| `question` | 待讨论 | PM 先澄清 |

---

## 流水线全景

```
PM 创建 Issue → requirement/{功能名} 分支 → merge master

  → feature/{N}-{task} 分支
    → develop 开发 → git tag round-N-dev → git push
      → test1 审查 → git tag round-N-review → git push --tags
        → integration 集成测试 → git tag round-N-itest → git push --tags
          → puppeteer UI 验证 → git tag round-N-ui → git push --tags
            → deploy 部署验证 → git merge master → git tag deploy-N → git push
```

**只有 deploy Agent 有权 merge master。**

---

## 角色与职责

| 角色 | 文件 | 入口 | 职责 |
|------|------|------|------|
| PM | pm.md | /start 1 | 需求分析、Issue 分诊、分支创建 |
| 框架架构 | develop1.md | /start 2 | 抽象接口、注册中心、编排器 |
| 功能开发 | develop2.md | /start 3 | Provider、API、前端 |
| BUG修复 | bugfixer.md | /start 4 | 只修 label:bug 的 Issue |
| 代码审查 | test1.md | /start 5 | 审查 + 单元测试 |
| 集成测试 | integration.md | /start 6 | 端到端验证 |
| 运维 | deploy.md | /start 7 | 健康检查 |
| 部署 | deploy.md | /start 8 | 部署 + merge master |
| UI测试 | puppeteer-agent.md | /start 9 | 浏览器拟人化测试 |

---

## Tag 体系

| Tag | 含义 | 谁打 |
|-----|------|:---:|
| `round-{N}-dev` | 开发完成 | develop |
| `round-{N}-review` | 审查通过 | test1 |
| `round-{N}-review-fail` | 审查不通过 | test1 |
| `round-{N}-itest` | 集成测试通过 | integration |
| `round-{N}-itest-fail` | 集成测试失败 | integration |
| `round-{N}-fix` | 修复完成，等回测 | bugfixer |
| `round-{N}-ui` | UI 验证通过 | puppeteer |
| `fix-BUG-XXX` | Bug 修复完成 | bugfixer |
| `deploy-{N}` | 部署完成 | deploy |

---

## 分支体系

| 类型 | 格式 | 创建者 |
|------|------|:---:|
| 需求 | `requirement/{功能名}` | PM |
| 功能 | `feature/{N}-{task}` | PM / develop |
| Bug修复 | `fix/BUG-XXX` | bugfixer |
| 审查修复 | `fix/{N}-review-fail` | bugfixer |
| 集成回测 | `fix/{N}-itest-fail` | integration |

---

## 各阶段操作

### 1. PM — 创建需求 + Issue 分诊
```bash
# 建 Issue
gh issue create --title "feat: {功能名}" --label enhancement

# 建需求分支
git checkout -b requirement/{功能名}
# 编写 requirements/{功能名}.md
git add requirements/
git commit -m "docs: {功能名} 需求文档"
git push origin requirement/{功能名}

# 需求通过
git checkout master && git merge requirement/{功能名} --no-ff
git push origin master

# 建开发分支
git checkout -b feature/{N}-{task}
git push origin feature/{N}-{task}
```

### 2. develop — 开发
```bash
git checkout master && git pull origin master
git checkout -b feature/{N}-{task}
git push origin feature/{N}-{task}
# 开发...
git add {files}
git commit -m "feat({N}): T-{编号} {描述}"
git push origin feature/{N}-{task}
# 完成
git tag round-{N}-dev
git push origin --tags
```

### 3. test1 — 审查
```bash
git fetch origin
git checkout feature/{N}-{task}
pytest tests/ -v
# 通过
git tag round-{N}-review && git push origin --tags
# 失败 → git tag round-{N}-review-fail → 告诉 PM 建 Issue
```

### 4. integration — 集成测试
```bash
git fetch origin && git checkout feature/{N}-{task}
# 测试...
# 通过
git tag round-{N}-itest && git push origin --tags
# 失败 → git tag round-{N}-itest-fail → git checkout -b fix/{N}-itest-fail → 告诉 PM
```

### 5. puppeteer — UI 验证
```bash
git fetch origin
# 有前端变更 → 测试 → git tag round-{N}-ui && git push origin --tags
# 无前端变更 → git tag round-{N}-ui && git push origin --tags（跳过测试）
# 发现 Bug → 告诉 PM 建 Issue
```

### 6. deploy — 部署
```bash
git checkout master && git pull origin master
# 先 merge 新代码（本地）再验证
git merge feature/{N}-{task} --no-ff
# 停服务 → 起服务 → 验证 5 个 API
# 通过
git tag deploy-{N} && git push origin master --tags
# 失败 → git reset --hard {回滚点}
```

---

## 提交规范

```
<type>(<scope>): <subject>
type: feat|fix|refactor|docs|chore|test|review|deploy
subject: 中文简述
```

Bug 修复必须含 `fixes #N`：`fix: BUG-112 修复序列化异常, fixes #88`

---

## 常用命令

```bash
# 流水线状态
git tag --list "round-*-dev"      # 待审查
git tag --list "round-*-review"   # 待集成测试
git tag --list "round-*-itest"    # 待部署
git tag --list "deploy-*"         # 已部署

# GitHub Issues
gh issue list --label bug --state open          # 待修复 Bug
gh issue list --label enhancement --state open  # 待开发需求
gh issue list --label question --state open     # 待讨论
```
