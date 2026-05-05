# AStock - A股数据采集分析系统

A股全市场数据采集、质量分析、K线可视化系统。模块化架构，数据层 → 应用层可扩展。

## 功能

- **股票基础信息采集** — 全市场 5500+ 股票，行业/地区/概念板块全覆盖
- **历史K线数据** — 日/周/月/季/年线，前复权，多数据源自动降级
- **实时行情** — 当日盘口数据，涨幅榜/跌幅榜/成交量榜
- **数据质量分析** — 完整度/新鲜度/异常检测，趋势图表
- **个股K线图** — KLineChart 深色主题，周期切换，技术指标
- **数据源管理** — 4 个 Provider（东方财富/新浪/腾讯/通达信），优先级/强制选择/启用禁用
- **概念板块** — 160+ 概念板块，股票多对多关联，hover tooltip

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 / FastAPI / SQLAlchemy |
| 数据库 | OceanBase (MySQL 兼容) |
| 前端 | Vue 3 + 原生 HTML / ECharts / KLineChart（本地） |
| 数据源 | AkShare / mootdx TCP |
| Agent | Claude Code 多角色协作 / Git tag 驱动 |

## 快速开始

```bash
pip install -r requirements.txt
python main.py init      # 初始化数据库
python main.py basic     # 采集基础信息
python web_app.py        # 启动服务 → http://localhost:8000
```

## 项目结构

```
stock/
├── modules/
│   └── collector/          ← 数据采集模块（当前唯一模块）
│       ├── adapters/       ←   数据源适配器（AkShare/mootdx）
│       ├── services/       ←   业务逻辑（编排器/质量/数据源管理）
│       ├── collectors/     ←   采集器（基础信息/K线/实时行情）
│       ├── web/            ←   前端（templates + Vue SPA + static）
│       ├── providers.yaml  ←   数据源配置
│       └── datasources.json←   自定义数据源
│
├── common/                 ← 跨模块共享（ORM 模型/配置/DB）
├── requirements/           ← 项目设计文档
│   ├── 模块设计规范.md
│   ├── 开发规范.md
│   └── collector/          ← collector 模块需求
├── scripts/                ← Agent 任务发现脚本
├── tests/                  ← 单元测试
│
├── web_app.py              ← FastAPI 主入口
├── main.py                 ← CLI 入口
├── config.py               ← 全局配置
├── utils.py                ← 工具函数
└── models.py               ← ORM 代理 → common/models.py
```

## 模块规划

| 模块 | 状态 | 职责 |
|------|:--:|------|
| **collector** | ✅ | 数据采集——所有后续模块的数据基础 |
| analysis | 🔮 | 股票分析——技术指标、趋势识别 |
| backtest | 🔮 | 股票回测——策略编写、历史回测 |
| labeling | 🔮 | 股票标签——涨停基因、连板、龙头识别 |

新模块从 `modules/collector/` 复制骨架起步，架构规范见 `requirements/模块设计规范.md`。

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /api/status` | 采集任务状态 |
| `GET /api/stocks` | 股票列表（含概念板块） |
| `GET /api/stock/{symbol}/kline` | K线数据（日/周/月/季/年） |
| `GET /api/quality/report` | 数据质量报告 |
| `GET /api/quality/trend` | 数据质量趋势 |
| `GET /api/concepts` | 概念板块列表 |
| `GET /api/concepts/{id}/stocks` | 概念板块成分股 |
| `GET /api/datasource/providers` | 数据源管理 |
| `POST /api/collect/{type}` | 触发采集 |
| `POST /api/stop` | 停止采集 |

## 开发工作流

Git tag 驱动 + PM 统一 Issue 分诊 + `bash scripts/check-*.sh` 确定性任务发现。

```
develop → review → itest → ui → deploy → 关 Issue
```

详见 `requirements/模块设计规范.md` 和 `.claude/commands/git-workflow.md`。

## License

MIT
