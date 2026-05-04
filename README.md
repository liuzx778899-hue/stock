# AStock - A股数据采集分析系统

A股全市场数据采集、质量分析、K线可视化系统。

## 功能

- **股票基础信息采集** — 全市场 5500+ 股票，行业/地区/概念板块全覆盖
- **历史K线数据** — 日/周/月/年线，前复权，多数据源自动降级
- **实时行情** — 当日盘口数据，涨幅榜/跌幅榜/成交量榜
- **数据质量分析** — 完整度/新鲜度/异常检测，趋势图表
- **个股K线图** — KLineChart 深色主题，BOLL/MACD/RSI 技术指标
- **数据源管理** — 4 个 Provider（东方财富/新浪/腾讯/通达信），优先级/强制选择

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 / FastAPI / SQLAlchemy |
| 数据库 | OceanBase (MySQL 兼容) |
| 前端 | Vue 3 + 原生 HTML/ECharts/KLineChart |
| 数据源 | AkShare / mootdx |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据库（复制 .env.example 为 .env 并填写）
cp .env.example .env

# 3. 初始化数据库表
python main.py init

# 4. 采集基础信息
python main.py basic

# 5. 启动服务
python web_app.py
# 访问 http://localhost:8000
```

## 项目结构

```
├── adapters/          # 数据源适配器（AkShare/mootdx）
├── collectors/        # 采集器（基础信息/K线/实时行情）
├── services/          # 业务服务（编排器/质量分析/字段合并）
├── templates/         # 前端页面
├── tests/             # 单元测试
├── requirements/      # 需求文档
├── web_app.py         # FastAPI 入口
├── main.py            # CLI 入口
├── config.py          # 配置
└── models.py          # ORM 模型
```

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /api/status` | 系统状态 |
| `GET /api/stocks` | 股票列表（支持搜索） |
| `GET /api/stock/{symbol}/kline` | 个股K线数据 |
| `GET /api/quality/report` | 数据质量报告 |
| `GET /api/quality/trend` | 数据质量趋势 |
| `GET /api/datasource/providers` | 数据源能力声明 |
| `POST /api/collect/{type}` | 触发采集任务 |

## 开发工作流

Git tag 驱动 + PM 统一 Issue 分诊。详见 `docs/git-workflow.html`。

## License

MIT