# 模块设计规范

## 目录约定

```
stock/
├── common/                  # 跨模块共享层
│   ├── models.py            #   ORM 模型（所有模块共用一张表结构）
│   ├── config.py            #   全局配置
│   └── db.py                #   数据库连接
│
├── adapters/                # 数据源适配器（共享）
│
├── scripts/                 # Agent 任务发现脚本（共享）
├── .claude/                 # Agent 配置
│
├── modules/                 # 业务模块
│   ├── collector/           #   数据采集
│   │   ├── __init__.py
│   │   ├── services/        #     业务逻辑
│   │   ├── collectors/      #     采集器
│   │   ├── web/             #     前端资源
│   │   │   ├── templates/
│   │   │   └── frontend/
│   │   └── requirements/    #     需求文档
│   │
│   ├── analysis/            #   【未来】股票分析
│   ├── backtest/            #   【未来】股票回测
│   └── labeling/            #   【未来】股票标签
│
├── web_app.py               # FastAPI 主入口
├── tests/
└── MODULE_DESIGN.md         # 本文件
```

## 模块隔离规则

1. **每个模块自包含**——services/collectors/web/requirements 都在自己目录下
2. **模块间通过 common 通信**——不直接 import 其他模块的 services
3. **共享层只放真正共享的**——ORM 模型、配置、数据库连接。模块特有逻辑不放 common
4. **新模块 = 复制目录骨架**——从 collector 或其他已有模块复制结构，改内容

## Agent 工作流兼容

Tag 加模块前缀：

```
现在（单模块）：       round-80-dev → review → itest → deploy
以后（多模块）：       collector-80-dev  /  analysis-1-dev  /  backtest-3-dev
```

脚本无需改动——tag 格式不变，模块名自然成为 tag 前缀。

## 迁移路径

当前代码处于过渡期：
- `models.py` 在根目录，内容代理到 `common/models.py`
- `services/` `collectors/` `templates/` 在根目录，逐步迁入 `modules/collector/`
- 新模块直接从 `modules/` 起步，不受旧结构影响
