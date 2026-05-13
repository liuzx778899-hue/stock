# Agent 协作流程图

```mermaid
flowchart TD
    U[用户反馈 / 新需求] --> PM

    subgraph PM[PM 产品经理]
        A1[查重 Issue] --> A2{存在?}
        A2 -->|是| A3[reopen + 评论]
        A2 -->|否| A4[新建 Issue + label]
        A4 --> A5[enhancement?]
        A5 -->|是| A6[写需求文档 + 建 feature 分支]
        A5 -->|bug?| A7[bugfixer 领]
    end

    A6 --> DEV

    subgraph DEV[develop1 / develop2]
        B1["bash .claude/scripts/dispatch.sh | grep role:develop"]
        B1 --> B2{有 JSON 行?}
        B2 -->|N>0| B3[checkout 分支 开发]
        B3 --> B4[commit: refs #N]
        B4 --> B5[git tag -a round-N-dev]
    end

    B5 --> TEST1

    subgraph TEST1[test1 代码审查]
        C1["bash .claude/scripts/dispatch.sh | grep role:test1"]
        C1 --> C2{有 JSON 行?}
        C2 -->|N>0| C3[pytest + 审查]
        C3 --> C4{通过?}
        C4 -->|是| C5[git tag -a round-N-review]
        C4 -->|否| C6[git tag -a round-N-review-fail]
    end

    C6 --> FIX

    subgraph FIX[bugfixer 修复]
        D1["bash .claude/scripts/dispatch.sh | grep role:bugfixer"]
        D1 --> D2{有 JSON 行?}
        D2 -->|N>0| D3[修复代码]
        D3 --> D4[commit: fixes #N]
        D4 --> D5[git tag -a fix-BUG-N]
        D5 --> C1
    end

    C5 --> INT

    subgraph INT[integration 集成测试]
        E1["bash .claude/scripts/dispatch.sh | grep role:integration"]
        E1 --> E2{有 JSON 行?}
        E2 -->|N>0| E3[端到端测试]
        E3 --> E4{通过?}
        E4 -->|是| E5[git tag -a round-N-itest]
        E4 -->|否| E6[git tag -a round-N-itest-fail]
    end

    E5 --> UI
    E6 --> EBUG[gh issue create + 建 fix/BUG-N 分支]

    subgraph UI[puppeteer UI验证]
        F1["bash .claude/scripts/dispatch.sh | grep role:puppeteer"]
        F1 --> F2{有 JSON 行?}
        F2 -->|N>0| F3[浏览器验证]
        F3 --> F4[git tag -a round-N-ui]
    end

    F4 --> DEPLOY

    subgraph DEPLOY[deploy 部署]
        G1["bash .claude/scripts/dispatch.sh | grep role:deploy"]
        G1 --> G2{有 JSON 行?}
        G2 -->|N>0| G3[git merge origin/分支]
        G3 --> G4[git tag -a deploy-N]
        G4 --> G5[提取 refs/fixes #N]
        G5 --> G6[gh issue close N]
    end

    G6 --> DONE[✅ 完成]

    A7 --> FIX
    EBUG --> FIX
```

## 角色对应

| 角色 | 命令 | 任务发现 | Tag |
|------|------|------|-----|
| PM | /start → 1 | — | req-{name} |
| develop1/2 | /develop | dispatch.sh \| grep develop | round-N-dev |
| test1 | /review /test | dispatch.sh \| grep test1 | round-N-review / -fail |
| bugfixer | /fix | dispatch.sh \| grep bugfixer | fix-BUG-N |
| integration | /integrationtest | dispatch.sh \| grep integration | round-N-itest / -fail |
| puppeteer | /puppeteer | dispatch.sh \| grep puppeteer | round-N-ui |
| deploy | /deploy | dispatch.sh \| grep deploy | deploy-N |

> 兜底：各角色也可用独立 `bash .claude/scripts/check-*.sh` 脚本输出人类可读格式；主入口始终是 `dispatch.sh` JSON。

## 异常路径

```
review-fail  → dispatch.sh 自动检测 → bugfixer 修复 → 重新走管线
itest-fail   → 集成测试先建 Issue → gh issue create → 建 fix/BUG-{N} 分支
              → bugfixer 修复打 fix-BUG-N tag → test1 审查 → integration 回测
僵尸任务     → 服务重启时自动重置 running=false
```

## 分支命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 需求 | requirement/{功能名} | requirement/db-encrypt |
| 功能 | feature/{N}-{task} | feature/154-t1-db-password-encrypt |
| 修复 | fix/BUG-{N} | fix/BUG-155 |

> ⚠️ 修复分支统一用 `fix/BUG-{N}`（Issue 编号），不使用 `fix/{轮次}-itest-fail`。
