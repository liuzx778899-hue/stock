# 开发规范

## 目录结构

每个模块内部统一：

```
modules/{name}/
├── __init__.py
├── services/           # 业务逻辑（一个文件一个职责）
├── web/                # 前端
│   ├── templates/      #   Jinja2 模板
│   └── frontend/       #   Vue SPA
└── requirements/       # 需求文档
```

## 命名

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | snake_case | `data_orchestrator.py` |
| 类名 | PascalCase | `DataOrchestrator` |
| 函数/方法 | snake_case | `get_kline()` |
| 私有方法 | _前缀 | `_aggregate_kline()` |
| 常量 | UPPER_SNAKE | `BUILTIN_DEFAULT_PRIORITIES` |

## 导入顺序

```python
# 1. 标准库
import json
from pathlib import Path

# 2. 第三方
from fastapi import FastAPI
import pandas as pd

# 3. 项目内部
from common.models import StockBasic
from adapters.registry import registry
from utils import logger
```

## 函数设计

- 一个函数只做一件事，不超过 50 行
- 参数不超过 5 个，多了用 dataclass 或 TypedDict
- 公开方法必须有类型标注
- 不写 docstring 描述"做了什么"——函数名已经说了。只在 WHY 不显然时写一行注释

```python
# ✅ 清晰
def get_kline(symbol: str, period: str = "day", limit: int = 200) -> dict:

# ❌ 啰嗦
def get_kline_data(symbol, period, limit):
    """获取K线数据"""
```

## 错误处理

```python
# ✅ 明确捕获
try:
    data = fetch_from_api(symbol)
except ConnectionError:
    logger.warning(f"API 连接失败: {symbol}")
    return None

# ❌ 裸 except
try:
    data = fetch_from_api(symbol)
except:
    pass
```

## 模块间通信

- 通过 `common/` 共享数据模型
- 不直接 import 其他模块的 services
- 需要跨模块调用 → 走 API 或 common 层接口

## 禁止事项

| 禁止 | 原因 |
|------|------|
| `import *` | 污染命名空间，不知道导入了什么 |
| 裸 `except:` | 吞掉 KeyboardInterrupt 和 SystemExit |
| 函数超过 100 行 | 拆成多个小函数 |
| 硬编码魔法数字 | 用命名常量 |
| 循环导入 | 提取公共依赖到 common |
| `pip install` 不更新 requirements.txt | 别人跑不起来 |

## Agent 开发额外规则

- commit 必须 `refs #N` 或 `fixes #N`
- 每个 git tag 带 JSON 附注
- 完成一个任务立即打 tag，不堆积
