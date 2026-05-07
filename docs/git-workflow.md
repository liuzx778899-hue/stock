# Git 驱动开发流程

## 概述

Git tag 管理任务全生命周期。Agent 之间无直接对话，通过 tag + Issue 传递状态。任务发现由 `bash .claude/scripts/check-*.sh` 确定性脚本驱动。

## 公共规则（所有角色）

1. **任务发现** — `bash .claude/scripts/check-*.sh`，输出 `>>> 待XX: N 个`，N>0 必须开工
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

develop → bash .claude/scripts/check-develop.sh 发现任务
  → checkout → 开发 → commit "feat(N): xxx, refs #N"
    → git tag -a round-N-dev -m '{JSON}'
      → test1 → bash .claude/scripts/check-review.sh 发现任务
        → 审查 → pytest → git tag -a round-N-review -m '{JSON}'
          → integration → bash .claude/scripts/check-integration.sh 发现任务
            → 集成测试 → git tag -a round-N-itest -m '{JSON}'
              → puppeteer → bash .claude/scripts/check-ui.sh 发现任务
                → UI验证 → git tag -a round-N-ui -m '{JSON}'
                  → deploy → bash .claude/scripts/check-deploy.sh 发现任务
                    → 从 BRANCH= 提取分支名 → git merge origin/{分支}
                      → git tag -a deploy-N -m '{JSON}'
                        → 提取 refs/fixes #N → gh issue close N ✅
```

Bug 链：
```
PM 建 bug Issue → bugfixer → bash .claude/scripts/check-fix.sh 发现任务
  → fix/BUG-N 分支 → commit "fix: xxx, fixes #N"
    → git tag -a fix-BUG-N -m '{JSON}'
      → test1 审查 → round-BUGN-review → itest → deploy → 关 Issue
```

## 任务发现脚本

所有脚本**只输出 TODO，不输出 DONE**，第一行以 `>>>` 开头给出最终判定：

| 脚本 | 使用者 | 查找逻辑 |
|------|--------|------|
| `.claude/scripts/check-develop.sh` | develop1/2 | 未开始的 enhancement Issue（排除已在 pipeline 的） + 未打 dev tag 的分支 |
| `.claude/scripts/check-review.sh` | test1 | dev tag 无 review 的 round + fix-BUG 无 review 的 |
| `.claude/scripts/check-integration.sh` | integration | review tag 无 itest 的 |
| `.claude/scripts/check-fix.sh` | bugfixer | bug Issue 无 fix 分支的 + fix tag 待审查的 |
| `.claude/scripts/check-ui.sh` | puppeteer | itest tag 无 ui 的 |
| `.claude/scripts/check-deploy.sh` | deploy | ui tag 无 deploy 的 + master 有代码但 Issue 未关的（输出 `BRANCH=` 分支名） |

**输出格式**：`>>> 待XX: N 个 — 必须立即开工 <<<` → 下一行起具体任务。N>0 必须开工，禁止 Agent 说"无任务"。

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
3. 同时 `check-deploy.sh` 检测已部署但 Issue 未关的任务

## 流程诊断

卡住时跑所有脚本检查断在哪一步：
```bash
bash .claude/scripts/check-develop.sh && bash .claude/scripts/check-review.sh && bash .claude/scripts/check-integration.sh && bash .claude/scripts/check-ui.sh && bash .claude/scripts/check-deploy.sh && bash .claude/scripts/check-fix.sh
```
