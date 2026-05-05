# 模块设计规范

## 模块注册表

| 模块 | 目录 | 状态 | 职责 |
|------|------|:--:|------|
| **collector** | `modules/collector/` | ✅ 运行中 | A股数据采集——股票基础信息、K线、实时行情、行业/地区/概念板块。所有后续模块的数据基础。 |
| analysis | `modules/analysis/` | 🔮 规划中 | 股票分析——技术指标、趋势识别、形态分析 |
| backtest | `modules/backtest/` | 🔮 规划中 | 股票回测——策略编写、历史回测、收益评估 |
| labeling | `modules/labeling/` | 🔮 规划中 | 股票标签——涨停基因、连板、龙头识别 |

## 依赖关系

```
common/  (ORM模型、配置、DB连接)
   ↑
collector/  (数据层——所有模块的数据来源)
   ↑
analysis/  backtest/  labeling/  (应用层——消费数据)
```

新模块只依赖 `common/` 和 `collector/` 提供的 API/数据，模块之间不直接引用。

## 目录约定

```
stock/
├── common/                  # 跨模块共享
│   ├── models.py            #   ORM 模型
│   ├── config.py            #   全局配置
│   └── db.py                #   数据库连接
│
├── scripts/                 # Agent 任务发现脚本
├── .claude/                 # Agent 配置
│
├── modules/
│   └── {name}/
│       ├── __init__.py      #   模块说明写在 docstring 里
│       ├── adapters/        #   数据源适配器（仅本模块用）
│       ├── services/        #   业务逻辑
│       ├── web/             #   前端资源
│       │   ├── templates/
│       │   └── frontend/
│       └── requirements/    #   需求文档
│
├── web_app.py               # FastAPI 主入口
├── tests/
├── MODULE_DESIGN.md         # 本文件
├── DEVELOPMENT_STANDARDS.md # 编码规范
└── CLAUDE.md                # AI 上下文
```

## 新模块启动清单

1. 复制 `modules/collector/__init__.py` 到 `modules/{name}/`，改 docstring
2. 创建 `services/` `web/` `requirements/` 子目录
3. 在 `web_app.py` 中挂载路由
4. 需求文档放 `modules/{name}/requirements/`
5. 打模块 tag 格式：`{name}-{round}-dev`

## 识别模块

每个 `modules/{name}/__init__.py` 的 docstring 说明模块职责：

```python
"""
collector - A股数据采集模块
职责: 采集股票基础信息、K线、实时行情、行业/地区/概念板块
依赖: common.models, adapters
提供给: analysis, backtest, labeling 的数据基础
"""
```
