# Git 驱动开发流程

## 概述

项目使用 Git hooks 自动化管理任务状态和测试流程。

## 安装

```bash
# Linux/Mac
bash scripts/install-hooks.sh

# Windows
scripts\install-hooks.bat
```

## Commit Message 规范

```
<type>: <description> #<round>-T<task>
```

### 类型 (type)
| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `refactor` | 重构 |
| `test` | 测试相关 |
| `chore` | 构建/工具 |

### 任务编号格式
| 格式 | 示例 |
|------|------|
| `#XX-TY` | `#54-T1` |
| 中文 | `(第五十四轮 T-2)` |

### 示例
```bash
feat: K线图升级 KLineChart #54-T2
fix: 质量检查日期参数 #53-T1
docs: 更新 API 文档
```

## Git Hooks

### post-commit
- 解析 commit message 中的任务编号
- 自动更新 `agent-tasks.md` 中任务状态

### pre-push
- 运行 `pytest tests/`
- 测试失败则阻止推送

### commit-msg
- 验证 commit message 格式
- 非法格式给出警告（不阻止提交）

## 工作流程

```
1. 开发代码
2. git add .
3. git commit -m "feat: xxx #54-T1"
   ↓
   post-commit hook → 更新 agent-tasks.md
4. git push
   ↓
   pre-push hook → 运行 pytest
   ↓
   成功 → 推送
   失败 → 阻止推送
```

## 跳过 Hooks

```bash
# 跳过 pre-push 测试
git push --no-verify

# 跳过 commit-msg 验证
git commit --no-verify -m "xxx"
```
