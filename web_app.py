"""
Web界面 - A股数据采集系统
FastAPI + WebSocket 实时进度推送
"""
import asyncio
import threading
import importlib
from datetime import datetime, time
from typing import List, Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import config
from models import Base, StockBasic
from utils import logger, TaskStoppedException
from sqlalchemy import text, inspect
from services.datasource_service import datasource_service, CustomDataSourceConfig

# 全局采集器（延迟初始化）
collector: Optional["StockDataCollector"] = None

# 采集器初始化锁（防止并发创建多个引擎）
collector_lock = asyncio.Lock()

# 任务锁（防止并发竞态）
task_lock = asyncio.Lock()

# 首页 HTML 缓存
_index_html_cache: Optional[str] = None

# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


# ==================== 类型转换工具 ====================

def _convert_numpy_types(obj):
    """转换 numpy 类型为 Python 原生类型（解决 JSON 序列化问题）"""
    import numpy as np
    import pandas as pd
    if obj is None:
        return None
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Series):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert_numpy_types(v) for v in obj]
    return obj


# 采集任务状态
task_status = {
    "running": False,
    "task_type": None,
    "progress": 0,
    "total": 0,
    "stats": None,
    "error": None
}

# 停止任务标志（使用线程安全的事件对象）
stop_requested = threading.Event()


class KlineRequest(BaseModel):
    start_date: str
    end_date: str
    threads: int = 10


class IncrementalRequest(BaseModel):
    days: int = 30


class DatabaseConfigRequest(BaseModel):
    host: str = "192.168.2.32"
    port: int = 2881
    username: str = "root@hdw"
    password: str
    database: str = "astock"


# ==================== Lifespan ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _index_html_cache
    logger.info("Web应用启动...")
    # 预加载首页 HTML 到内存缓存
    html_path = Path(__file__).parent / "templates" / "index.html"
    if html_path.exists():
        _index_html_cache = html_path.read_text(encoding="utf-8")
        logger.info("首页 HTML 已缓存")
    else:
        logger.warning(f"首页模板不存在: {html_path}")
    yield
    logger.info("Web应用关闭")


# 创建 FastAPI 应用
app = FastAPI(title="A股数据采集系统", version="1.0.0", lifespan=lifespan)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ==================== 页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面 - 返回缓存的静态 HTML"""
    global _index_html_cache
    if _index_html_cache:
        return HTMLResponse(content=_index_html_cache)
    # 缓存未命中，尝试从文件读取
    html_path = Path(__file__).parent / "templates" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)


# ==================== API 路由 ====================

@app.get("/api/status")
async def get_status():
    """获取采集任务状态"""
    return _convert_numpy_types(task_status)


# ==================== 数据库连接 API ====================

@app.get("/api/db/status")
async def get_db_status():
    """获取数据库连接状态"""
    global collector

    # 检查是否已连接
    if collector is None:
        return {
            "connected": False,
            "tables_exist": False,
            "tables": [],
            "message": "未连接数据库，请先在 Settings 页面配置连接信息"
        }

    try:
        # 测试连接
        with collector.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # 检查表是否存在
        inspector = inspect(collector.engine)
        existing_tables = inspector.get_table_names()
        required_tables = ['stock_basic', 'stock_daily_kline', 'stock_realtime_quote', 'collect_log']
        tables_exist = all(t in existing_tables for t in required_tables)

        return {
            "connected": True,
            "tables_exist": tables_exist,
            "tables": existing_tables,
            "message": "数据库连接正常" if tables_exist else "数据库已连接，表结构未初始化"
        }
    except Exception as e:
        return {
            "connected": False,
            "tables_exist": False,
            "tables": [],
            "message": f"连接失败: {str(e)}"
        }


@app.post("/api/db/connect")
async def db_connect(db_config: DatabaseConfigRequest):
    """测试数据库连接并保存配置"""
    global collector

    try:
        # 创建临时引擎测试连接（复用 DatabaseConfig URL 构建逻辑）
        from sqlalchemy import create_engine
        from config import DatabaseConfig
        temp_db = DatabaseConfig(
            host=db_config.host, port=db_config.port,
            username=db_config.username, password=db_config.password,
            database=db_config.database
        )

        engine = create_engine(temp_db.connection_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        # 测试成功，销毁临时引擎
        engine.dispose()

        # 更新 .env 文件保存配置（供后续启动使用）
        env_path = Path(__file__).parent / ".env"
        env_content = f"""# 数据库配置
DB_HOST={db_config.host}
DB_PORT={db_config.port}
DB_USER={db_config.username}
DB_PASSWORD={db_config.password}
DB_NAME={db_config.database}
"""
        env_path.write_text(env_content, encoding="utf-8")

        # 重新加载配置模块并创建采集器
        import config as config_mod
        importlib.reload(config_mod)

        from main import StockDataCollector
        collector = StockDataCollector()

        return {"success": True, "message": "数据库连接成功，配置已保存到 .env 文件"}
    except Exception as e:
        return {"success": False, "message": f"连接失败: {str(e)}"}


@app.post("/api/db/init")
async def db_init():
    """初始化数据库表结构"""
    global collector

    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    try:
        Base.metadata.create_all(collector.engine)
        return {"success": True, "message": "表结构初始化成功"}
    except Exception as e:
        return {"success": False, "message": f"初始化失败: {str(e)}"}


# ==================== 数据源管理 API ====================
# 注意：这些端点无认证保护，仅限内部使用。生产环境请添加认证（BUG-058 说明）


class DataSourceBase(BaseModel):
    """数据源基础字段（用于复用，修复代码重复问题）"""
    name: Optional[str] = None
    type: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    headers: Optional[dict] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    auth_type: Optional[str] = None
    auth_header: Optional[str] = None
    request_method: Optional[str] = None
    request_template: Optional[dict] = None
    response_parser: Optional[str] = None


class DataSourceUpdateRequest(DataSourceBase):
    """数据源更新请求（修复 BUG-057）"""
    pass


@app.get("/api/datasource/list")
async def list_datasources():
    """获取所有数据源列表（内置 + 自定义）"""
    return {"sources": datasource_service.list_all()}


@app.get("/api/datasource/options")
async def get_datasource_options():
    """获取数据源下拉选项（修复 BUG-081）"""
    sources = datasource_service.list_all()
    return {"sources": sources}


@app.post("/api/datasource/add")
async def add_datasource(source: CustomDataSourceConfig):
    """添加自定义数据源"""
    try:
        added = datasource_service.add(source)
        # 排除 api_key 字段（修复 BUG-056）
        return {"success": True, "message": "数据源添加成功", "source": added.model_dump(exclude={'api_key'})}
    except Exception as e:
        return {"success": False, "message": f"添加失败: {str(e)}"}


@app.put("/api/datasource/{source_id}")
async def update_datasource(source_id: str, updates: DataSourceUpdateRequest):
    """更新数据源配置"""
    # 使用 Pydantic model 替代 raw dict（修复 BUG-057）
    update_dict = {k: v for k, v in updates.model_dump().items() if v is not None}
    updated = datasource_service.update(source_id, update_dict)
    if updated:
        # 排除 api_key 字段（修复 BUG-056）
        return {"success": True, "message": "数据源更新成功", "source": updated.model_dump(exclude={'api_key'})}
    return {"success": False, "message": "数据源不存在"}


@app.delete("/api/datasource/{source_id}")
async def remove_datasource(source_id: str):
    """删除自定义数据源"""
    if datasource_service.remove(source_id):
        return {"success": True, "message": "数据源已删除"}
    return {"success": False, "message": "数据源不存在或无法删除"}


@app.post("/api/datasource/test")
async def test_datasource(source: CustomDataSourceConfig):
    """测试数据源连通性"""
    result = datasource_service.test_connection(source)
    return result


@app.get("/api/datasource/current")
async def get_current_datasource():
    """获取当前使用的数据源（修复 BUG-081：返回格式匹配前端期望）"""
    from adapters import registry
    forced = datasource_service.get_forced_source()
    # 返回前端期望的格式
    return {
        "is_forced": forced is not None,
        "current_source": datasource_service.get_current_source_name(),
        "forced_source": forced,
        "available": [p.provider_name for p in registry.get_all_providers()]
    }


class ForceDataSourceRequest(BaseModel):
    provider: Optional[str] = None


@app.post("/api/datasource/force")
async def force_datasource(request: ForceDataSourceRequest):
    """强制使用指定数据源（传空恢复自动模式）"""
    if request.provider:
        datasource_service.set_forced_source(request.provider)
        return {"success": True, "mode": "forced", "provider": request.provider}
    else:
        datasource_service.set_forced_source(None)
        return {"success": True, "mode": "auto", "provider": None}


# ==================== 内置数据源优先级管理 (修复 BUG-083) ====================

class PriorityRequest(BaseModel):
    priority: int


@app.put("/api/datasource/builtin/{name}/priority")
async def update_builtin_priority(name: str, request: PriorityRequest):
    """更新内置数据源优先级"""
    if request.priority < 1 or request.priority > 100:
        return {"success": False, "message": "优先级必须在 1-100 之间"}
    success = datasource_service.update_builtin_priority(name, request.priority)
    if success:
        return {"success": True, "message": f"数据源 {name} 优先级已更新为 {request.priority}"}
    return {"success": False, "message": f"数据源 {name} 不存在或无法更新"}


@app.post("/api/datasource/builtin/{name}/reset")
async def reset_builtin_priority(name: str):
    """重置内置数据源优先级为默认值"""
    success = datasource_service.reset_builtin_priority(name)
    if success:
        return {"success": True, "message": f"数据源 {name} 优先级已重置"}
    return {"success": False, "message": f"数据源 {name} 不存在或无法重置"}


# ==================== Provider 能力声明 API (T7-1) ====================

@app.get("/api/datasource/providers")
async def get_provider_capabilities():
    """返回所有 Provider 能力声明列表"""
    from adapters import registry
    return registry.get_capabilities_report()


# ==================== 字段覆盖率报告 API (T7-2) ====================

@app.get("/api/collect/field-report")
async def get_field_coverage_report():
    """返回最近一次采集的字段覆盖率报告"""
    from services.data_orchestrator import orchestrator
    report = orchestrator.get_field_report()
    return report if report else {"message": "暂无采集数据"}


# ==================== 必盈 API 管理 ====================

@app.get("/api/biying/status")
async def get_biying_status():
    """获取必盈 Licence 状态"""
    from adapters.biying import get_biying_status
    return {"licences": get_biying_status()}


class BiyingAddRequest(BaseModel):
    licence: str


@app.post("/api/biying/add")
async def add_biying_licence(request: BiyingAddRequest):
    """添加必盈 Licence"""
    from adapters.biying import add_biying_licence
    try:
        add_biying_licence(request.licence)
        return {"success": True, "message": "Licence 添加成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.delete("/api/biying/{licence}")
async def remove_biying_licence(licence: str):
    """删除必盈 Licence"""
    from adapters.biying import remove_biying_licence
    try:
        remove_biying_licence(licence)
        return {"success": True, "message": "Licence 已删除"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/biying/test")
async def test_biying_api():
    """测试必盈 API 连接"""
    from adapters.biying import BiyingProvider
    try:
        provider = BiyingProvider()
        result = provider.health_check()
        return {"success": result, "message": "连接成功" if result else "连接失败"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# ==================== 日志管理 API ====================

@app.get("/api/logs/list")
async def list_logs():
    """获取日志文件列表"""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {"logs": []}
    logs = []
    for f in sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True):
        logs.append({
            "name": f.name,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        })
    return {"logs": logs}


class LogSearchRequest(BaseModel):
    keyword: str
    file: Optional[str] = None


@app.get("/api/logs/search")
async def search_logs(keyword: str = "", file: Optional[str] = None):
    """搜索日志内容"""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {"results": []}
    results = []
    files = [log_dir / file] if file else log_dir.glob("*.log")
    for f in (files if isinstance(files, list) else files):
        if not f.exists():
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines()):
                if keyword.lower() in line.lower():
                    results.append({"file": f.name, "line": i + 1, "content": line[:200]})
                    if len(results) >= 100:
                        break
        except Exception:
            continue
    return {"results": results}


@app.get("/api/logs/content")
async def get_log_content(filename: str, lines: int = 100, offset: int = 0):
    """读取日志文件内容（倒序，最新日志在前）"""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {"success": False, "message": "日志目录不存在"}

    # 安全检查：防止路径遍历
    safe_filename = Path(filename).name
    log_file = log_dir / safe_filename

    if not log_file.exists():
        return {"success": False, "message": "日志文件不存在"}

    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        # 倒序读取（最新日志在前）
        reversed_lines = list(reversed(all_lines))

        start = offset
        end = min(offset + lines, total_lines)
        content = [line.rstrip('\n\r') for line in reversed_lines[start:end]]

        return {
            "success": True,
            "content": content,
            "start": start,
            "end": end,
            "total_lines": total_lines
        }
    except Exception as e:
        return {"success": False, "message": f"读取失败: {str(e)}"}


class LogCleanupRequest(BaseModel):
    days: int = 7


@app.post("/api/logs/cleanup")
async def cleanup_logs(request: LogCleanupRequest):
    """清理旧日志"""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {"deleted_count": 0, "deleted_files": []}
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=request.days)
    deleted = []
    for f in log_dir.glob("*.log"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            try:
                f.unlink()
                deleted.append(f.name)
            except Exception:
                pass
    return {"deleted_count": len(deleted), "deleted_files": deleted, "cutoff_date": cutoff.isoformat()}


@app.get("/api/stats")
async def get_stats():
    """获取数据统计"""
    global collector
    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    session = Session(bind=collector.engine)
    try:
        from sqlalchemy import text

        # 股票数量
        stock_count = session.query(StockBasic).count()

        # K线记录数
        kline_count = session.execute(text("SELECT COUNT(*) FROM stock_daily_kline")).scalar() or 0

        # 实时行情记录数
        realtime_count = session.execute(text("SELECT COUNT(*) FROM stock_realtime_quote")).scalar() or 0

        # 采集日志数
        log_count = session.execute(text("SELECT COUNT(*) FROM collect_log")).scalar() or 0

        return {
            "stock_count": stock_count,
            "kline_count": kline_count,
            "realtime_count": realtime_count,
            "log_count": log_count
        }
    finally:
        session.close()


@app.get("/api/stocks")
async def get_stocks(search: Optional[str] = None, limit: int = 100):
    """获取股票列表（支持搜索）"""
    global collector
    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    session = Session(bind=collector.engine)
    try:
        query = session.query(StockBasic)

        # 搜索过滤
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (StockBasic.ts_code.ilike(search_pattern)) |
                (StockBasic.name.ilike(search_pattern)) |
                (StockBasic.industry.ilike(search_pattern)) |
                (StockBasic.area.ilike(search_pattern))
            )

        total = query.count()
        stocks = query.limit(limit).all()

        return {
            "total": total,
            "stocks": [
                {
                    "ts_code": s.ts_code,
                    "symbol": s.ts_code.split('.')[0] if s.ts_code else '',
                    "name": s.name,
                    "industry": s.industry,
                    "area": s.area
                }
                for s in stocks
            ]
        }
    finally:
        session.close()


@app.post("/api/collect/basic")
async def collect_basic(background_tasks: BackgroundTasks):
    """采集股票基础信息"""
    global collector, task_status

    async with task_lock:
        if task_status["running"]:
            return {"success": False, "error": "有任务正在运行中"}

        task_status["running"] = True
        task_status["task_type"] = "basic"
        task_status["progress"] = 0
        task_status["error"] = None

    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    background_tasks.add_task(run_collect_basic)

    return {"success": True, "message": "股票基础信息采集任务已启动"}


@app.post("/api/collect/kline")
async def collect_kline(request: KlineRequest, background_tasks: BackgroundTasks):
    """采集历史K线数据"""
    global collector, task_status

    async with task_lock:
        if task_status["running"]:
            return {"success": False, "error": "有任务正在运行中"}

        task_status["running"] = True
        task_status["task_type"] = "kline"
        task_status["progress"] = 0
        task_status["total"] = 0
        task_status["error"] = None

    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    background_tasks.add_task(
        run_collect_kline,
        request.start_date,
        request.end_date,
        request.threads
    )

    return {
        "success": True,
        "message": f"K线采集任务已启动: {request.start_date} - {request.end_date}"
    }


@app.post("/api/collect/incremental")
async def collect_incremental(request: IncrementalRequest, background_tasks: BackgroundTasks):
    """增量采集最近N天数据"""
    global collector, task_status

    async with task_lock:
        if task_status["running"]:
            return {"success": False, "error": "有任务正在运行中"}

        task_status["running"] = True
        task_status["task_type"] = "incremental"
        task_status["progress"] = 0
        task_status["error"] = None

    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    background_tasks.add_task(run_collect_incremental, request.days)

    return {"success": True, "message": f"增量采集任务已启动: 最近 {request.days} 天"}


@app.post("/api/collect/realtime")
async def collect_realtime(background_tasks: BackgroundTasks):
    """采集实时行情"""
    global collector, task_status

    async with task_lock:
        if task_status["running"]:
            return {"success": False, "error": "有任务正在运行中"}

        task_status["running"] = True
        task_status["task_type"] = "realtime"
        task_status["progress"] = 0
        task_status["error"] = None

    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    background_tasks.add_task(run_collect_realtime)

    return {"success": True, "message": "实时行情采集任务已启动"}


class ForceStopRequest(BaseModel):
    force: bool = False


@app.post("/api/stop")
async def stop_task(request: Optional[ForceStopRequest] = None):
    """停止采集任务"""
    global stop_requested, task_status

    if not task_status["running"]:
        return {"success": False, "error": "当前没有运行中的任务"}

    # 检查是否强制停止
    force = request and request.force

    stop_requested.set()

    if force:
        # 强制重置状态（用于卡死场景）
        async with task_lock:
            task_status["running"] = False
            task_status["error"] = "任务被强制停止"
            stop_requested.clear()
        await broadcast_status("stopped", "任务已被强制停止")
        return {"success": True, "message": "任务已被强制停止，状态已重置"}

    return {"success": True, "message": "已发送停止信号，任务将在当前批次完成后停止"}


@app.get("/api/market/status")
async def get_market_status():
    """获取市场开闭盘状态"""
    now = datetime.now()
    current_time = now.time()

    # 从配置获取交易日和交易时间
    trading_hours = config.trading_hours
    weekday = now.weekday()

    # 判断是否为交易日
    if weekday not in trading_hours.trading_days:
        return {
            "is_trading": False,
            "reason": "非交易日（周末）",
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S")
        }

    # 从配置解析交易时间
    morning_open = datetime.strptime(trading_hours.morning_start, "%H:%M").time()
    morning_close = datetime.strptime(trading_hours.morning_end, "%H:%M").time()
    afternoon_open = datetime.strptime(trading_hours.afternoon_start, "%H:%M").time()
    afternoon_close = datetime.strptime(trading_hours.afternoon_end, "%H:%M").time()

    is_trading = (morning_open <= current_time <= morning_close) or \
                 (afternoon_open <= current_time <= afternoon_close)

    if is_trading:
        reason = "交易时间"
    elif current_time < morning_open:
        reason = "开盘前"
    elif morning_close < current_time < afternoon_open:
        reason = "午间休市"
    elif current_time > afternoon_close:
        reason = "已收盘"
    else:
        reason = "非交易时间"

    return {
        "is_trading": is_trading,
        "reason": reason,
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "next_action": "开盘" if current_time < morning_open else ("下午开盘" if morning_close < current_time < afternoon_open else "明日开盘")
    }


@app.post("/api/collect/realtime-auto")
async def collect_realtime_auto(background_tasks: BackgroundTasks):
    """智能采集实时行情（自动判断是否开盘）"""
    global collector, task_status

    # 检查是否开盘
    market_status = await get_market_status()
    if not market_status["is_trading"]:
        return {
            "success": False,
            "error": f"当前非交易时间（{market_status['reason']}），不采集实时行情",
            "market_status": market_status
        }

    async with task_lock:
        if task_status["running"]:
            return {"success": False, "error": "有任务正在运行中"}

        task_status["running"] = True
        task_status["task_type"] = "realtime"
        task_status["progress"] = 0
        task_status["error"] = None

    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    background_tasks.add_task(run_collect_realtime)

    return {"success": True, "message": "实时行情采集任务已启动", "market_status": market_status}


# ==================== WebSocket ====================

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket 进度推送"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ==================== 后台任务 ====================

def _make_kline_progress_callback(loop):
    """创建K线采集进度回调，通过 WebSocket 广播进度，支持停止检查"""
    def callback(completed, total, stats):
        # 检查是否请求停止
        if stop_requested.is_set():
            raise TaskStoppedException("用户请求停止任务")

        percent = round(completed * 100 / total, 1) if total > 0 else 0
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "progress",
                "completed": completed,
                "total": total,
                "percent": percent,
                "stats": stats,
                "message": f"进度: {completed}/{total} ({percent}%), 已采集 {stats.get('total_records', 0)} 条"
            }),
            loop
        )
    return callback


def _make_basic_progress_callback(loop):
    """创建基础信息采集进度回调（修复 BUG-082）"""
    def callback(current, total, stage):
        # 检查是否请求停止
        if stop_requested.is_set():
            raise TaskStoppedException("用户请求停止任务")

        percent = round(current * 100 / total, 1) if total > 0 else 0
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "progress",
                "completed": current,
                "total": total,
                "percent": percent,
                "stage": stage,
                "message": f"{stage}: {current}/{total} ({percent}%)"
            }),
            loop
        )
    return callback


async def run_collect_basic():
    """后台运行：采集股票基础信息"""
    global task_status, stop_requested

    try:
        await broadcast_status("progress", "开始采集股票基础信息...")
        task_status["progress"] = 0
        task_status["total"] = 0

        if stop_requested.is_set():
            await broadcast_status("stopped", "任务已停止")
            return

        loop = asyncio.get_event_loop()
        # 创建进度回调（修复 BUG-082）
        progress_cb = _make_basic_progress_callback(loop)
        # 传递进度回调和停止检查回调
        count = await loop.run_in_executor(
            None,
            lambda: collector.collect_stock_basic(
                progress_callback=progress_cb,
                stop_check=stop_requested.is_set
            )
        )

        if stop_requested.is_set():
            await broadcast_status("stopped", "任务已停止")
            return

        task_status["stats"] = _convert_numpy_types({"count": count})
        task_status["progress"] = count
        task_status["total"] = count
        await broadcast_status("completed", f"采集完成，共 {count} 条记录")

    except TaskStoppedException:
        await broadcast_status("stopped", "任务已停止")
    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()


async def run_collect_kline(start_date: str, end_date: str, threads: int):
    """后台运行：采集历史K线"""
    global task_status, stop_requested

    try:
        collector.kline_collector.thread_pool_size = threads

        await broadcast_status("progress", f"开始采集K线数据: {start_date} ~ {end_date}")
        task_status["progress"] = 0
        task_status["total"] = 0

        loop = asyncio.get_event_loop()

        # 使用进度回调通过 WebSocket 推送实时进度
        progress_cb = _make_kline_progress_callback(loop)
        try:
            stats = await loop.run_in_executor(
                None,
                lambda: collector.kline_collector.collect(
                    start_date, end_date,
                    progress_callback=progress_cb
                )
            )
        except TaskStoppedException:
            await broadcast_status("error", "任务已停止")
            return

        task_status["stats"] = _convert_numpy_types(stats)
        task_status["progress"] = stats.get("total", 0)
        task_status["total"] = stats.get("total", 0)
        await broadcast_status("completed", f"采集完成，共 {stats.get('total_records', 0)} 条记录")

    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()


async def run_collect_incremental(days: int):
    """后台运行：增量采集"""
    global task_status, stop_requested

    try:
        await broadcast_status("progress", f"开始增量采集最近 {days} 天数据...")
        task_status["progress"] = 0
        task_status["total"] = 0

        loop = asyncio.get_event_loop()

        # 使用进度回调通过 WebSocket 推送实时进度
        progress_cb = _make_kline_progress_callback(loop)
        try:
            stats = await loop.run_in_executor(
                None,
                lambda: collector.kline_collector.collect_incremental(days, progress_callback=progress_cb)
            )
        except TaskStoppedException:
            await broadcast_status("error", "任务已停止")
            return

        task_status["stats"] = _convert_numpy_types(stats)
        task_status["progress"] = stats.get("total", 0)
        task_status["total"] = stats.get("total", 0)
        await broadcast_status("completed", f"增量采集完成，共 {stats.get('total_records', 0)} 条记录")

    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()


async def run_collect_realtime():
    """后台运行：采集实时行情"""
    global task_status, stop_requested

    try:
        await broadcast_status("progress", "开始采集实时行情...")
        task_status["progress"] = 0
        task_status["total"] = 0

        if stop_requested.is_set():
            await broadcast_status("stopped", "任务已停止")
            return

        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            None,
            lambda: collector.collect_realtime_quote('em')
        )

        if stop_requested.is_set():
            await broadcast_status("stopped", "任务已停止")
            return

        task_status["stats"] = _convert_numpy_types(stats)
        task_status["progress"] = stats.get("total", 0)
        task_status["total"] = stats.get("total", 0)
        await broadcast_status("completed", f"实时行情采集完成，共 {stats.get('total', 0)} 条记录")

    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()


# ==================== 辅助函数 ====================

async def broadcast_status(status_type: str, message: str):
    """广播状态更新"""
    await manager.broadcast({
        "type": status_type,
        "message": message,
        "timestamp": datetime.now().isoformat()
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)