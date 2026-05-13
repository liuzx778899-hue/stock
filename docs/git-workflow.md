# Git 驱动开发流程

## 概述

Git tag 管理任务全生命周期。Agent 之间无直接对话，通过 tag + Issue 传递状态。

**任务发现入口**：`bash .claude/scripts/dispatch.sh` — 统一 JSON 输出，按 `role` 字段指派。每个角色只处理自己的行；`check-*.sh` 仅作为人类可读兜底。

## 公共规则（所有角色）

1. **任务发现** — `bash .claude/scripts/dispatch.sh | grep '"role":"{role}"'`，有 JSON 行必须开工
2. **提交身份** — `git config user.name "角色名"`
3. **结构化 Tag** — `git tag -a` + JSON 附注
4. **Issue 引用** — develop 用 `refs #N`，bugfixer 用 `fixes #N`
5. **建分支** — 先 `git pull origin master`
6. **合并后清理** — 删远程分支
7. **推送** — PowerShell: `git push origin --tags --no-verify`

## 流水线

```
PM 建 Issue + 需求文档 → requirement/{功能名}
  → 需求通过 → feature/{N}-{task} 分支

dispatch.sh ──┬─ role:develop → checkout → 开发 → commit "feat(N): xxx, refs #N"
    → git tag -a round-N-dev -m '{JSON}'
              │
              ├─ role:test1 → 审查 → pytest → round-N-review / round-N-review-fail
              │
              ├─ role:integration → 集成测试 → round-N-itest / round-N-itest-fail
              │
              ├─ role:puppeteer → UI验证 → round-N-ui
              │
              ├─ role:deploy → 从 JSON branch 提取分支名 → git merge origin/{分支}
              │    → git tag -a deploy-N -m '{JSON}' → 提取 refs/fixes #N → gh issue close N ✅
              │
              └─ role:bugfixer → fix/BUG-N 分支 → commit "fix: xxx, fixes #N"
                   → git tag -a fix-BUG-N -m '{JSON}' → test1 审查
```

Bug 链：
```
PM 建 bug Issue → dispatch.sh 输出 role:bugfixer
  → fix/BUG-N 分支 → commit "fix: xxx, fixes #N"
    → git tag -a fix-BUG-N -m '{JSON}'
      → test1 审查 → round-BUGN-review → itest → deploy → 关 Issue
```

## dispatch.sh — 统一任务指派（JSON）

```bash
bash .claude/scripts/dispatch.sh
```

输出每行一个 JSON 对象，Agent 按 `role` 字段认领：

```json
{"role":"develop","issue":74,"task":"质量页面","branch":"feature/74-t1","reason":"新enhancement"}
{"role":"bugfixer","issue":140,"task":"数据库连接失败","branch":null,"reason":"新bug"}
{"role":"test1","issue":74,"task":"审查 round-74-dev","branch":"feature/74-t1","reason":"dev完成"}
{"role":"integration","issue":74,"task":"集成测试 round-74","branch":null,"reason":"review通过"}
{"role":"puppeteer","issue":74,"task":"UI验证 round-74","branch":null,"reason":"itest通过"}
{"role":"deploy","issue":74,"task":"部署 deploy-74","branch":"feature/74-t1","reason":"ui通过"}
```

| role | 触发条件 | 后续动作 |
|------|---------|---------|
| `develop` | 新 enhancement Issue / feature 分支无 dev tag | 开发 → round-N-dev |
| `bugfixer` | 新 bug Issue / review-fail 打回 | 修复 → fix-BUG-N（不关 Issue） |
| `test1` | dev tag 无 review / fix-BUG tag 无 review | 审查 → round-N-review 或 review-fail |
| `integration` | review tag 无 itest（排除 fail） | 集成测试 → round-N-itest 或 itest-fail |
| `puppeteer` | itest tag 无 ui（排除 fail） | UI 验证 → round-N-ui |
| `deploy` | ui tag 无 deploy | merge → deploy-N → 关 Issue |

**is_deployed() 过滤器**：dispatch.sh 内每个阶段都先检查 `deploy-N` tag 是否存在，已部署的轮次自动跳过。

## 各角色任务发现命令

| 角色 | 命令 | 说明 |
|------|------|------|
| develop1/2 | `bash .claude/scripts/dispatch.sh \| grep '"role":"develop"'` | 只取开发任务 |
| bugfixer | `bash .claude/scripts/dispatch.sh \| grep '"role":"bugfixer"'` | 只取修复任务 |
| test1 | `bash .claude/scripts/dispatch.sh \| grep '"role":"test1"'` | 只取审查任务 |
| integration | `bash .claude/scripts/dispatch.sh \| grep '"role":"integration"'` | 只取集成测试任务 |
| puppeteer | `bash .claude/scripts/dispatch.sh \| grep '"role":"puppeteer"'` | 只取 UI 验证任务 |
| deploy | `bash .claude/scripts/dispatch.sh \| grep '"role":"deploy"'` | 提取 JSON `branch` 做 merge |

> 同时保留独立 `check-*.sh` 脚本作为兜底，输出人类可读的 `>>> 待XX: N 个` 格式。

## Tag 规范

所有 tag 使用 `git tag -a` + JSON 附注：

| Tag | 含义 | 谁打 | 附注关键字段 |
|-----|------|:---:|------|
| `round-{N}-dev` | 开发完成 | develop | task_id, summary, files_changed, next_expected_tag |
| `round-{N}-review` | 审查通过 | test1 | review_conclusion, warnings |
| `round-{N}-review-fail` | 审查不通过 | test1 | warnings (必填失败原因) |
| `round-{N}-itest` | 集成测试通过 | integration | tests_total, tests_passed, tests_failed |
| `round-{N}-itest-fail` | 集成测试失败 | integration | tests_failed, warnings |
| `round-{N}-ui` | UI 验证通过 | puppeteer | screenshots |
| `fix-BUG-XXX` | Bug 修复完成 | bugfixer | task_id, issue, files_changed |
| `deploy-{N}` | 部署完成 | deploy | deploy_time, rollback_commit, issues |

## Commit 规范

```
feat(N): T-{编号} {描述}, refs #{Issue编号}    ← develop 必须 refs #N
fix: BUG-XXX {描述}, fixes #{Issue编号}        ← bugfixer 必须 fixes #N
```

> `refs #N` / `fixes #N` 是 deploy 自动关 Issue 的唯一依据，缺了关不掉。

## 分支规范

| 类型 | 格式 | 负责 |
|------|------|:---:|
| 需求 | requirement/{功能名} | PM |
| 功能 | feature/{N}-{task} | develop |
| 修复 | fix/BUG-{N} | bugfixer |

> 合并到 master 后删除远程分支，只保留 master。

## 项目架构

```
stock/
├── common/              ← 共享层（models / config / utils）
├── modules/
│   └── collector/       ← 数据采集模块
│       ├── adapters/    ←   数据源适配器
│       ├── services/    ←   业务逻辑
│       ├── collectors/  ←   采集器
│       ├── web/         ←   前端（templates / frontend / static）
│       ├── providers.yaml
│       └── datasources.json
├── requirements/        ← 项目设计文档
│   ├── 模块设计规范.md
│   ├── 开发规范.md
│   └── collector/       ←   collector 需求文档
├── .claude/scripts/     ← Agent 任务发现
├── tests/
├── web_app.py           ← FastAPI 主入口
└── config.py utils.py models.py  ← 根代理 → common/
```

| 设计文档 | 用途 |
|------|------|
| `requirements/模块设计规范.md` | 模块注册表 + 目录约定 + 依赖关系 |
| `requirements/开发规范.md` | 编码规范（命名、导入、函数设计、禁止事项） |
| `modules/collector/__init__.py` | collector 模块 docstring 标识 |

## Agent 角色

| # | 角色 | 文件 | 命令 |
|---|------|------|------|
| 0 | 系统架构师 / PM | pm.md | /start → 1 |
| 1 | 框架架构 | develop1.md | /develop |
| 2 | 功能开发 | develop2.md | /develop |
| 3 | BUG 修复 | bugfixer.md | /fix |
| 4 | 代码审查&测试 | test1.md | /review, /test |
| 5 | 集成测试 | integration.md | /integrationtest |
| 6 | 部署 | deploy.md | /deploy |
| 7 | UI 验证 | puppeteer-agent.md | /puppeteer |

## PM Issue 规则

1. 建 Issue 前先 `gh search issues` 查重，存在则 reopen 不新建
2. enhancement → 建需求文档 + feature 分支（commit 含 `refs #N`）
3. bug → bugfixer 修（commit 含 `fixes #N`）
4. question → 讨论后转标签
5. 架构设计 → `requirement/{name}` 分支，产出 MODULE_DESIGN 等设计文档

## 部署自动关 Issue

deploy Agent 合并分支后自动：
1. `git log master` 提取 `refs #N` / `fixes #N`
2. `gh issue close N`
3. `deploy-N` tag 写入后，`dispatch.sh` 的 `is_deployed()` 过滤器会自动跳过已部署轮次

## 流程诊断

卡住时先看统一分派输出：
```bash
bash .claude/scripts/dispatch.sh
```

需要人类可读摘要时，再跑 `check-*.sh` 兜底脚本。
