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
        B1[bash check-develop.sh]
        B1 --> B2{>>> 待开发: N 个}
        B2 -->|N>0| B3[checkout 分支 开发]
        B3 --> B4[commit: refs #N]
        B4 --> B5[git tag -a round-N-dev]
    end

    B5 --> TEST1

    subgraph TEST1[test1 代码审查]
        C1[bash check-review.sh]
        C1 --> C2{>>> 待审查: N 个}
        C2 -->|N>0| C3[pytest + 审查]
        C3 --> C4{通过?}
        C4 -->|是| C5[git tag -a round-N-review]
        C4 -->|否| C6[git tag -a round-N-review-fail]
    end

    C6 --> FIX

    subgraph FIX[bugfixer 修复]
        D1[bash check-fix.sh]
        D1 --> D2{>>> 待修复: N 个}
        D2 -->|N>0| D3[修复代码]
        D3 --> D4[commit: fixes #N]
        D4 --> D5[git tag -a fix-BUG-N]
        D5 --> C1
    end

    C5 --> INT

    subgraph INT[integration 集成测试]
        E1[bash check-integration.sh]
        E1 --> E2{>>> 待集成测试: N 个}
        E2 -->|N>0| E3[端到端测试]
        E3 --> E4{通过?}
        E4 -->|是| E5[git tag -a round-N-itest]
        E4 -->|否| E6[git tag -a round-N-itest-fail]
    end

    E6 --> FIX
    E5 --> UI

    subgraph UI[puppeteer UI验证]
        F1[bash check-ui.sh]
        F1 --> F2{>>> 待 UI 验证: N 个}
        F2 -->|N>0| F3[浏览器验证]
        F3 --> F4[git tag -a round-N-ui]
    end

    F4 --> DEPLOY

    subgraph DEPLOY[deploy 部署]
        G1[bash check-deploy.sh]
        G1 --> G2{>>> 待部署: N 个}
        G2 -->|N>0| G3[git merge origin/分支]
        G3 --> G4[git tag -a deploy-N]
        G4 --> G5[提取 refs/fixes #N]
        G5 --> G6[gh issue close N]
    end

    G6 --> DONE[✅ 完成]

    A7 --> FIX
```

## 角色对应

| 角色 | 命令 | 脚本 | Tag |
|------|------|------|-----|
| PM | /start → 1 | — | req-{name} |
| develop1/2 | /develop | check-develop.sh | round-N-dev |
| test1 | /review /test | check-review.sh | round-N-review / -fail |
| bugfixer | /fix | check-fix.sh | fix-BUG-N |
| integration | /integrationtest | check-integration.sh | round-N-itest / -fail |
| puppeteer | /puppeteer | check-ui.sh | round-N-ui |
| deploy | /deploy | check-deploy.sh | deploy-N |

## 异常路径

```
review-fail  → check-fix.sh 自动检测 → bugfixer 修复 → 重新打 dev tag → 重新走管线
itest-fail   → check-fix.sh 自动检测 → bugfixer 修复 → 重新走管线
僵尸任务     → 服务重启时自动重置 running=false
```
