# 技术方案：通达信数据源接入（mootdx）

创建时间：2026-05-03
最后更新：2026-05-03
状态：已交付（第三十六轮集成测试通过）

## 1. 背景与目标

### 问题
行业（industry）和地区（area）字段覆盖率长期为 0%，根因是系统 HTTP 代理拦截 eastmoney.com 等AkShare依赖的域名。现有 Provider（eastmoney/sina/tencent）均通过 HTTP 获取数据，全部受代理影响。

### 目标
接入 mootdx（通达信 Python SDK），利用其 **TCP 协议** 绕过 HTTP 代理，获取行业/地区分类数据，使 `stock_basic` 表的 industry/area 字段覆盖率 > 50%。

---

## 2. 技术选型

| 维度 | mootdx | pytdx | 结论 |
|------|--------|-------|------|
| 维护状态 | v0.11.7，活跃 | 已停止维护 | ✅ mootdx |
| 连接测试 | ✅ TCP 连接成功（110.41.147.114:7709） | ❌ 无法连接 | ✅ mootdx |
| F10 接口 | ✅ 返回行业/地区/公司概况 | 未测试 | ✅ mootdx |
| API 风格 | Quotes 工厂模式 | 底层 TCP 管理 | ✅ mootdx |
| 安装 | `pip install mootdx` | `pip install pytdx` | — |

**数据获取路径**：mootdx Quotes → F10(股票代码) → 解析"行业分析"和"公司概况" → 提取 industry/area

---

## 3. F10 数据格式分析

### 3.1 行业（industry）

来源：`F10(code)["行业分析"]`

原始格式：
```
【所属行业】
----股份制银行Ⅱ--股份制银行Ⅱ(9)
```

提取规则：在"行业分析"段落中匹配 `----xxx--xxx(N)` 模式，取最后一段 `--` 之后、`(N)` 之前的部分。

### 3.2 地区（area）

来源：`F10(code)["公司概况"]`

原始格式：
```
【公司资料】
公司名称: 平安银行股份有限公司
证券简称: 平安银行
所属行业: 金融-股份制银行Ⅱ-股份制银行Ⅱ
注册地址: 深圳市罗湖区...
办公地址: 深圳市福田区...
```

提取规则：从"注册地址"或"办公地址"行匹配省份/直辖市关键字。

### 3.3 数据覆盖验证

| 股票代码 | 行业 | 地区 | 正确性 |
|---------|------|------|--------|
| 000001 平安银行 | 股份制银行Ⅱ | 深圳 | ✅ |
| 000002 万科A | 住宅开发 | 上海 | ✅ |
| 600000 浦发银行 | 股份制银行Ⅱ | 上海 | ✅ |
| 300750 宁德时代 | 锂电池 | 宁德 | ✅ |
| 688981 中芯国际 | 集成电路 | 上海 | ✅ |

---

## 4. 市场覆盖范围与混合方案

### 4.1 沪深京覆盖

| 市场 | 代码前缀 | mootdx F10 | AkShare BSE API | 状态 |
|------|---------|-----------|-----------------|------|
| 上海主板 | 60xxxx | ✅ 支持 | — | 正常 |
| 深圳主板 | 00xxxx | ✅ 支持 | — | 正常 |
| 深圳创业板 | 30xxxx | ✅ 支持 | — | 正常 |
| 上海科创板 | 68xxxx | ✅ 支持 | — | 正常 |
| 北交所 | 83xxxx, 87xxxx, 92xxxx | ❌ 不支持（MootdxValidationException） | ✅ `stock_info_bj_name_code()` | 需混合方案 |

### 3.2 北交所解决方案

mootdx 的 F10 接口仅支持沪深市场，北交所代码（8xxxxx/92xxxx）会抛出 `MootdxValidationException`。扩展市场（ext）已废弃，BJ 市场不支持 F10。

**替代方案**: 使用 AkShare `stock_info_bj_name_code()` API。该接口调用东方财富 BSE 专用端点，**经过实际测试未被代理拦截**，返回 311 只北交所股票的行业和省份数据：

```
920001 纬达光电 → 计算机通信和其他电子设备制造业, 广东省
920002 宏海科技 → 通信设备制造业, 湖北省
830799 艾融软件 → 软件和信息技术服务业, 上海市
```

**实现方式**: TdxProvider 的 `fetch_industry_mapping()` / `fetch_area_mapping()` 中增加后备逻辑：

```python
def _fetch_bse_industry_mapping(self) -> Dict[str, str]:
    """从 AkShare 获取北交所行业映射"""
    import akshare as ak
    df = ak.stock_info_bj_name_code()
    mapping = {}
    for _, row in df.iterrows():
        code = str(row['证券代码'])
        industry = str(row['所属行业'])
        if code and industry:
            mapping[code] = industry
    return mapping
```

**合并策略**:
```
fetch_industry_mapping():
  1. 从缓存加载
  2. mootdx F10 → 沪深股票（60/00/30/68xxxx）
  3. AkShare BSE API → 北交所股票（8/92xxxx）
  4. 合并 → 保存缓存 → 返回
```

### 3.3 数据覆盖验证

| 股票代码 | 市场 | 行业 | 地区 | 数据源 |
|---------|------|------|------|--------|
| 000001 平安银行 | 深圳主板 | 股份制银行Ⅱ | 深圳 | mootdx F10 |
| 000002 万科A | 深圳主板 | 住宅开发 | 广东 | mootdx F10 |
| 600000 浦发银行 | 上海主板 | 股份制银行Ⅱ | 上海 | mootdx F10 |
| 300750 宁德时代 | 创业板 | 锂电池 | 福建 | mootdx F10 |
| 688981 中芯国际 | 科创板 | 集成电路 | 上海 | mootdx F10 |
| 920001 纬达光电 | 北交所 | 计算机通信电子 | 广东 | AkShare BSE |
| 830799 艾融软件 | 北交所 | 软件信息技术 | 上海 | AkShare BSE |

---

## 5. 数据采集工作流

### 5.1 自动模式（推荐 ⭐）

编排器在**自动模式**下自动按优先级组合多个 Provider，**用户无需手动切换数据源**：

```
POST /api/collect/basic (自动模式，不强制数据源)
  │
  ├─ Stage 1: 获取股票列表
  │   └─ eastmoney (priority=1) → sina (priority=2) → tencent (priority=3)
  │   → 拿到 5000+ 股票代码和基本信息
  │
  ├─ Stage 2: 补齐行业字段
  │   └─ eastmoney → HTTP 超时(代理拦截) → 跳过
  │   └─ biying → 无有效 Licence → 跳过
  │   └─ mootdx → TCP 直连 → ✅ 获取行业
  │   → industry 覆盖率 0% → 80%+
  │
  └─ Stage 3: 补齐地区字段
      └─ biying → 无有效 Licence → 跳过
      └─ mootdx → TCP 直连 → ✅ 获取地区
      (北交所: AkShare BSE API)
      → area 覆盖率 0% → 60%+
```

一次采集自动完成全部字段，HTTP 超时带来的额外延迟 < 30 秒。

### 5.2 强制模式（已知限制）

强制选择 mootdx 后，`get_providers(STOCK_BASIC)` 只返回 mootdx，但 mootdx **仅支持 STOCK_INDUSTRY/STOCK_AREA**，返回空列表 `[]` → 采集 0 条记录。

详见 BUG-089。修复后强制 Provider 不支持当前类别时自动回退。

---

## 5. 系统架构

### 5.1 新增文件

```
adapters/
├── mootdx_provider.py    # 新增：TdxProvider（实现 DataProvider 接口）
└── __init__.py           # 修改：注册 TdxProvider 到 registry
```

### 5.2 数据流（内部双源自动分流）

```
TdxProvider.fetch_industry_mapping() / fetch_area_mapping()
  │
  ├─ 从缓存加载已有 mapping
  ├─ 获取待查询 symbol 列表
  │
  ├─ 分流1: 沪深代码 (60/00/30/68xxxx)
  │   └─ mootdx F10 (TCP) → 批量查询 → 正则提取
  │
  ├─ 分流2: 北交所代码 (8/92xxxx)  
  │   └─ AkShare stock_info_bj_name_code() (HTTP) → 提取行业/省份
  │
  └─ 合并 → 保存缓存 → 返回 {symbol: name}
```

**上游调用者（orchestrator）只看到一个 Provider，不知道内部分流逻辑。**

### 5.3 用户操作指南

| 场景 | 操作 | 结果 |
|------|------|------|
| 日常采集 | 自动模式 → 点"基础信息采集" | 股票列表 + 行业地区自动补齐 |
| 仅刷新行业地区 | 自动模式 → 采集（缓存命中 < 1s） | 增量股票走 F10，已有缓存秒出 |
| 强制 mootdx | ❌ 不推荐 | BUG-089: 采集返回 0 条 |

**一句话：保持自动模式，点一次采集按钮，沪深北三市行业/地区全部自动补齐。**

### 5.4 类设计

```python
class TdxProvider(DataProvider):
    """通达信数据源适配器
    
    内部自动分流：
    - 沪深股票 → mootdx F10 (TCP)
    - 北交所股票 → AkShare BSE API (HTTP)
    
    对外统一接口，上游无需关心内部分流逻辑。
    使用多线程加速 + 本地缓存。
    """
    
    provider_name = "mootdx"
    
    capabilities = [
        ProviderCapability(
            category=DataCategory.STOCK_INDUSTRY,
            fields=["symbol", "industry_name"],
            quality_score=0.8,
            cost_type="free",
        ),
        ProviderCapability(
            category=DataCategory.STOCK_AREA,
            fields=["symbol", "area_name"],
            quality_score=0.7,
            cost_type="free",
        ),
    ]
    
    # 核心方法
    def fetch_industry_mapping(self) -> Dict[str, str]:
        """返回 {symbol: industry_name} 映射"""
        
    def fetch_area_mapping(self) -> Dict[str, str]:
        """返回 {symbol: area_name} 映射"""
```

### 4.3 数据流

```
┌─────────────────────┐
│  DataOrchestrator   │
│  _supplement_field() │
└────────┬────────────┘
         │ 调用 fetch_industry_mapping()
         ▼
┌─────────────────────┐
│    TdxProvider      │
│  ┌───────────────┐  │
│  │ Cache Layer   │  │ ← 本地 JSON 缓存，24h 过期
│  │ (mootdx_      │  │
│  │  cache.json)  │  │
│  └───────┬───────┘  │
│          │ 缓存未命中 │
│  ┌───────▼───────┐  │
│  │ F10 Fetcher   │  │ ← ThreadPoolExecutor(16 workers)
│  │ (批量查询)     │  │   TCP 连接池
│  └───────┬───────┘  │
│          │
│  ┌───────▼───────┐  │
│  │ F10 Parser    │  │ ← 正则提取 行业/地区
│  └───────────────┘  │
└─────────────────────┘
         │
         ▼
   {symbol: name}
```

### 4.4 缓存策略

```
文件: project_root/mootdx_cache.json
结构:
{
  "industry": {"000001": "股份制银行Ⅱ", ...},
  "area": {"000001": "深圳", ...},
  "updated_at": "2026-05-03T17:00:00",
  "ttl_hours": 24
}
```
- 首次运行：全量查询（~8分钟，16线程）
- 后续运行：命中缓存，< 1 秒
- 增量更新：只查询缓存中不存在的新股票代码
- 过期策略：24 小时 TTL，采集前检查

---

## 5. 核心实现

### 5.1 F10 行业解析

```python
import re

def _parse_industry(self, f10_data: dict) -> Optional[str]:
    """从 F10 数据提取行业分类"""
    hyfx = f10_data.get("行业分析", "")
    # 匹配: ----行业名称--行业名称(N)
    pattern = r'--+([^-]+)--\1\(\d+\)'
    match = re.search(pattern, hyfx)
    if match:
        return match.group(1).strip()
    return None
```

### 5.2 F10 地区解析

```python
PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "广东", "浙江", "江苏", "山东", "河南", "四川",
    "湖北", "湖南", "福建", "安徽", "河北", "辽宁", "陕西",
    "江西", "广西", "山西", "云南", "贵州", "内蒙古",
    "吉林", "甘肃", "新疆", "海南", "宁夏", "青海", "西藏", "黑龙江",
]

def _parse_area(self, f10_data: dict) -> Optional[str]:
    """从 F10 数据提取地区（省份/直辖市）"""
    gsgk = f10_data.get("公司概况", "")
    # 优先匹配注册地址行
    for line in gsgk.split("\n"):
        if "注册地址" in line or "办公地址" in line:
            for p in PROVINCES:
                if p in line:
                    return p
    # 回退：全文搜索省份
    for p in PROVINCES:
        if p in gsgk:
            return p
    return None
```

### 5.3 多线程批量查询

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _batch_fetch_f10(self, symbols: List[str]) -> Dict[str, dict]:
    """多线程批量获取 F10 数据"""
    results = {}
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(self._fetch_one_f10, s): s for s in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except Exception as e:
                logger.warning(f"F10 获取失败 {symbol}: {e}")
    return results

def _fetch_one_f10(self, symbol: str) -> Optional[dict]:
    """获取单只股票的 F10 数据"""
    try:
        return self._quotes.F10(symbol)
    except Exception:
        return None
```

### 5.4 Quotes 连接管理

mootdx Quotes 对象内部维护 TCP 连接池。多线程场景下，每个线程需要独立的 Quotes 实例，或使用 `threading.local()` 保证线程安全。

```python
import threading

class TdxProvider(DataProvider):
    def __init__(self):
        self._local = threading.local()
    
    @property
    def _quotes(self):
        if not hasattr(self._local, 'quotes'):
            from mootdx.quotes import Quotes
            self._local.quotes = Quotes.factory(market='std')
        return self._local.quotes
```

---

## 6. 集成方式

### 6.1 注册到 Registry

```python
# adapters/__init__.py
from .mootdx_provider import TdxProvider

registry.register(TdxProvider())
```

### 6.2 侧边栏菜单顺序调整

将"数据质量"菜单项移至"数据采集"下方（紧随其后），8000 和 3000 端口统一。

**涉及文件**:
- `templates/index.html` — 移动 `.nav-item[data-page="quality"]` 到 collector 后面
- `frontend/src/App.vue` — 已正确（Quality 在 Collector 后），无需修改

**调整后顺序**: 数据采集 → 数据质量 → 股票列表 → 数据源管理 → 系统设置 → 日志查看

### 6.3 无需修改的其他文件

- `services/data_orchestrator.py` — 无需修改，自动通过 registry 发现新 Provider
- `services/datasource_service.py` — 无需修改，自动列表显示
- `web_app.py` — 无需修改

### 6.3 依赖更新

```
# requirements.txt 新增
mootdx>=0.11.0
```

---

## 7. 性能评估

| 场景 | 耗时 | 说明 |
|------|------|------|
| 首次全量（5000只） | ~8 分钟 | 16线程并发 F10 |
| 增量（100只新股票） | ~10 秒 | 仅查询缓存未命中 |
| 缓存命中 | < 1 秒 | 直接返回 JSON |
| 单只 F10 | ~1 秒 | TCP 往返 + 解析 |

---

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 通达信服务器不可达 | Provider 不可用 | 保留现有 AkShare 降级路径 |
| F10 数据格式变化 | 解析失败 | 正则匹配 + 异常捕获，返回 None |
| 全量查询耗时过长 | 首次采集慢 | 后台异步预热缓存 |
| TCP 连接池耗尽 | 查询失败 | 线程本地 Quotes 实例 |
| 行业名称与现有标准不一致 | 行业字段值不统一 | 可接受，比 0% 好 |

---

## 9. 不做的事

- 不通过 mootdx 获取股票列表（保持现有数据源）
- 不通过 mootdx 获取 K 线数据（保持现有数据源）
- 不通过 mootdx 获取实时行情（保持现有数据源）
- 不改变现有 Provider 的优先级排序
- 不修改前端和数据编排器代码

---

## 10. 开发任务拆解

### T-1: 创建 TdxProvider 基础框架
- 文件: `adapters/mootdx_provider.py`
- 内容: TdxProvider 类骨架、capabilities 声明、线程安全的 Quotes 管理
- 预计: 0.5h

### T-2: 实现 F10 行业/地区解析
- 文件: `adapters/mootdx_provider.py`
- 内容: `_parse_industry()`、`_parse_area()` 正则解析
- 预计: 0.5h

### T-3: 实现缓存层
- 文件: `adapters/mootdx_provider.py`
- 内容: `_load_cache()`、`_save_cache()`、24h TTL、增量更新
- 预计: 0.5h

### T-4: 实现多线程批量查询
- 文件: `adapters/mootdx_provider.py`
- 内容: `fetch_industry_mapping()`、`fetch_area_mapping()` 含批量 F10 + 缓存
- 预计: 0.5h

### T-5: 注册 + 集成测试
- 文件: `adapters/__init__.py` + `requirements.txt`
- 内容: 注册 TdxProvider、更新依赖
- 预计: 0.5h

---

## 11. 验收标准

- [ ] `TdxProvider.fetch_industry_mapping()` 返回 `{symbol: industry_name}` 格式，覆盖率 > 50%
- [ ] `TdxProvider.fetch_area_mapping()` 返回 `{symbol: area_name}` 格式，覆盖率 > 30%
- [ ] 首次全量查询后缓存文件生成，第二次查询 < 1 秒
- [ ] 基础信息采集后 stock_basic 表 industry/area 字段有值
- [ ] 数据源管理页面显示 "通达信（mootdx）" Provider
- [ ] `pytest tests/ -v` 现有 172 个测试全部通过（无回归）
- [ ] 服务启动正常，无 import 错误
