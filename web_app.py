"""
Web界面 - A股数据采集系统
FastAPI + WebSocket 实时进度推送
"""
import asyncio
import threading
import importlib
import re
from datetime import datetime, time
from typing import Any, List, Optional, Dict
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import config
from models import Base, StockBasic
from utils import logger, TaskStoppedException
from sqlalchemy import text, inspect
from modules.collector.services.datasource_service import datasource_service, CustomDataSourceConfig

# 全局采集器（延迟初始化）
collector: Optional["StockDataCollector"] = None

# 采集器初始化锁（防止并发创建多个引擎）
collector_lock = asyncio.Lock()

# 任务锁（防止并发竞态）
task_lock = asyncio.Lock()


# ==================== 辅助函数 ====================

def _batch_get_stock_concepts(session, symbols: List[str]) -> Dict[str, List[str]]:
    """批量获取股票关联的概念板块名称

    Args:
        session: 数据库会话
        symbols: 股票代码列表

    Returns:
        {symbol: [concept_name1, concept_name2, ...]}
    """
    if not symbols:
        return {}
    try:
        from models import Concept, StockConcept
        results = session.query(StockConcept.symbol, Concept.name).join(
            Concept, Concept.id == StockConcept.concept_id
        ).filter(StockConcept.symbol.in_(symbols)).all()

        concept_map: Dict[str, List[str]] = {}
        for symbol, name in results:
            if symbol not in concept_map:
                concept_map[symbol] = []
            if len(concept_map[symbol]) < 10:
                concept_map[symbol].append(name)
        return concept_map
    except Exception:
        return {}

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
    global _index_html_cache, task_status
    logger.info("Web应用启动...")
    # 确保采集状态为初始值（防止重启后僵尸状态）
    task_status.update({
        "running": False,
        "task_type": None,
        "progress": 0,
        "total": 0,
        "stats": None,
        "error": None
    })
    # 预加载首页 HTML 到内存缓存
    # 优先从 collector 模块加载，兼容旧路径
    html_path = Path(__file__).parent / "modules" / "collector" / "web" / "templates" / "index.html"
    if not html_path.exists():
        html_path = Path(__file__).parent / "modules" / "collector" / "web" / "templates" / "index.html"
    if html_path.exists():
        _index_html_cache = html_path.read_text(encoding="utf-8")
        logger.info(f"首页 HTML 已缓存: {html_path}")
    else:
        logger.warning(f"首页模板不存在")
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

# 挂载静态文件目录（第七十三轮：本地K线图库）
app.mount("/static", StaticFiles(directory="modules/collector/web/static"), name="static")



# ==================== 页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页面 - 返回缓存的静态 HTML"""
    global _index_html_cache
    if _index_html_cache:
        return HTMLResponse(content=_index_html_cache)
    # 缓存未命中，尝试从文件读取
    html_path = Path(__file__).parent / "modules" / "collector" / "web" / "templates" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)


@app.get("/db-config", response_class=HTMLResponse)
async def db_config_page():
    """数据库配置页面"""
    global _index_html_cache
    if _index_html_cache:
        return HTMLResponse(content=_index_html_cache)
    html_path = Path(__file__).parent / "modules" / "collector" / "web" / "templates" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Page not found</h1>", status_code=404)


# ==================== API 路由 ====================

@app.get("/api/status")
async def get_status():
    """获取采集任务状态"""
    return _convert_numpy_types(task_status)


# ==================== 数据库配置 API ====================

@app.get("/api/db-config")
async def get_db_config():
    """获取数据库连接配置（密码脱敏，优先DB > 本地文件）"""
    from common.db_config_store import load_local, load_from_db, DEFAULT_CONFIG

    config = None
    # 优先从数据库读取
    if collector and collector.engine:
        config = load_from_db(collector.engine)
    # 回退到本地文件
    if not config:
        config = load_local()
    if config:
        # 密码脱敏：显示为 ****
        masked_config = {
            "host": config.get("host", DEFAULT_CONFIG["host"]),
            "port": config.get("port", DEFAULT_CONFIG["port"]),
            "username": config.get("username", DEFAULT_CONFIG["username"]),
            "database": config.get("database", DEFAULT_CONFIG["database"]),
            "password": "****" if config.get("password") else "",
            "has_password": bool(config.get("password")),
        }
        return {"success": True, "config": masked_config}
    else:
        # 返回默认值
        return {
            "success": True,
            "config": {
                "host": DEFAULT_CONFIG["host"],
                "port": DEFAULT_CONFIG["port"],
                "username": DEFAULT_CONFIG["username"],
                "database": DEFAULT_CONFIG["database"],
                "password": "",
                "has_password": False,
            }
        }


class DbConfigSaveRequest(BaseModel):
    host: str = "192.168.2.32"
    port: int = 2881
    username: str = "root@hdw"
    password: str = ""
    database: str = "astock"


@app.post("/api/db-config")
async def save_db_config(request: DbConfigSaveRequest):
    """保存数据库连接配置（加密存储到本地文件 + system_config 表）"""
    from common.db_config_store import save_local, save_to_db, load_local

    # 如果密码为空或为 ****，保留旧密码
    config_to_save = {
        "host": request.host,
        "port": request.port,
        "username": request.username,
        "database": request.database,
    }

    if request.password and request.password != "****":
        # 新密码
        config_to_save["password"] = request.password
    else:
        # 保留旧密码
        existing = load_local()
        if existing and existing.get("password"):
            config_to_save["password"] = existing["password"]

    save_local(config_to_save)

    # 同步写入 system_config 表（如果数据库已连接）
    db_saved = False
    if collector and collector.engine:
        try:
            save_to_db(collector.engine, config_to_save)
            db_saved = True
        except Exception as e:
            logger.warning("保存到 system_config 表失败: %s", e)

    msg = "数据库配置已保存" + ("（本地 + 数据库）" if db_saved else "（仅本地文件）")
    return {"success": True, "message": msg}


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
    """获取数据源下拉选项（修复 BUG-081，排除禁用的 Provider）"""
    from modules.collector.adapters import registry
    all_sources = datasource_service.list_all()
    # 过滤禁用的 Provider
    enabled_sources = [s for s in all_sources if s.get('enabled', True)]
    return {"sources": enabled_sources}


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
    from modules.collector.adapters import registry
    forced = datasource_service.get_forced_source()
    # 返回前端期望的格式
    return {
        "is_forced": forced is not None,
        "current_source": datasource_service.get_current_source_name(),
        "forced_source": forced,
        "available": [p.provider_name for p in registry.get_all_providers()]
    }


class ForceDataSourceRequest(BaseModel):
    source_name: Optional[str] = None


@app.post("/api/datasource/force")
async def force_datasource(request: ForceDataSourceRequest):
    """强制使用指定数据源（传空恢复自动模式）"""
    if request.source_name:
        datasource_service.set_forced_source(request.source_name)
        display_name = datasource_service.get_display_name(request.source_name)
        return {"success": True, "mode": "forced", "provider": request.source_name,
                "message": f"已强制使用数据源：{display_name}"}
    else:
        datasource_service.set_forced_source(None)
        return {"success": True, "mode": "auto", "provider": None,
                "message": "已恢复自动选择数据源"}


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


class ToggleRequest(BaseModel):
    enabled: bool


@app.post("/api/datasource/toggle/{name}")
async def toggle_datasource(name: str, request: ToggleRequest):
    """启用/禁用数据源"""
    from modules.collector.adapters import registry
    success = registry.set_enabled(name, request.enabled)
    if success:
        status = "启用" if request.enabled else "禁用"
        return {"success": True, "message": f"数据源 {name} 已{status}", "enabled": request.enabled}
    return {"success": False, "message": f"数据源 {name} 不存在"}


# ==================== Provider 能力声明 API (T7-1) ====================

@app.get("/api/datasource/providers")
async def get_provider_capabilities():
    """返回所有 Provider 能力声明列表"""
    from modules.collector.adapters import registry
    return registry.get_capabilities_report()


# ==================== 字段覆盖率报告 API (T7-2) ====================

@app.get("/api/collect/field-report")
async def get_field_coverage_report():
    """返回最近一次采集的字段覆盖率报告"""
    from modules.collector.services.data_orchestrator import orchestrator
    report = orchestrator.get_field_report()
    return report if report else {"message": "暂无采集数据"}


# ==================== 数据质量 API (Q-3) ====================

@app.get("/api/quality/report")
async def get_quality_report(category: Optional[str] = None, date: Optional[str] = None):
    """获取质量检查报告

    Args:
        category: 可选，指定数据类别
        date: 可选，格式 YYYY-MM-DD，不传则返回最新报告
    """
    from sqlalchemy.orm import Session
    from modules.collector.services.data_quality import QualityService
    from config import config

    from sqlalchemy import create_engine
    engine = create_engine(config.database.connection_url)
    session = Session(bind=engine)
    try:
        service = QualityService(session)
        reports = service.get_latest_report(category, target_date=date)
        return {
            "check_time": reports[0]['check_time'] if reports else None,
            "reports": reports
        }
    finally:
        session.close()


@app.post("/api/quality/check")
async def trigger_quality_check(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """触发质量检查，支持日期区间批量生成报告

    Args:
        start_date: 开始日期（可选，格式 YYYY-MM-DD）
        end_date: 结束日期（可选，格式 YYYY-MM-DD）

    Returns:
        检查结果：单次检查返回单个报告，区间检查返回多个报告
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine
    from modules.collector.services.data_quality import QualityService
    from config import config
    from datetime import datetime as dt

    engine = create_engine(config.database.connection_url)
    session = Session(bind=engine)
    try:
        service = QualityService(session)
        loop = asyncio.get_running_loop()

        # 判断是区间检查还是单次检查
        if start_date and end_date:
            # 区间检查：对每一天生成报告
            from datetime import date
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            results = await loop.run_in_executor(None, service.check_range, start, end)
            message = f"区间检查完成 ({start_date} ~ {end_date})"
        else:
            # 单次检查：当前时间
            results = await loop.run_in_executor(None, service.check_all)
            await loop.run_in_executor(None, service.save_report, results)
            message = "质量检查完成"

        # 广播质量更新通知
        await manager.broadcast({
            "type": "quality_update",
            "message": message,
            "reports": results
        })

        return {
            "check_time": datetime.now().isoformat(),
            "reports": results,
            "message": message
        }
    finally:
        session.close()


@app.get("/api/quality/history")
async def get_quality_history(category: Optional[str] = None, limit: int = 20):
    """获取历史质量检查记录"""
    from sqlalchemy.orm import Session
    from modules.collector.services.data_quality import QualityService
    from config import config

    from sqlalchemy import create_engine
    engine = create_engine(config.database.connection_url)
    session = Session(bind=engine)
    try:
        service = QualityService(session)
        history = service.get_history(category, limit)
        return {"history": history}
    finally:
        session.close()


@app.get("/api/quality/trend")
async def get_quality_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None
):
    """获取质量趋势数据

    Args:
        start_date: 起始日期 YYYY-MM-DD（默认 30 天前）
        end_date: 结束日期 YYYY-MM-DD（默认今天）
        category: 可选，指定数据类别
    """
    from sqlalchemy.orm import Session
    from modules.collector.services.data_quality import QualityService
    from config import config

    from sqlalchemy import create_engine
    engine = create_engine(config.database.connection_url)
    session = Session(bind=engine)
    try:
        service = QualityService(session)
        trend = service.get_trend(start_date, end_date, category)
        return trend
    finally:
        session.close()


# ==================== 质量检查记录 API (#150) ====================

@app.get("/api/quality/records")
async def get_quality_records(start_date: str, end_date: str):
    """查询质量检查记录（只读数据库）

    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine, select
    from config import config
    from common.models import QualityCheckRecord
    from datetime import date

    engine = create_engine(config.database.connection_url)
    session = Session(bind=engine)
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        records = session.query(QualityCheckRecord).filter(
            QualityCheckRecord.check_date >= start,
            QualityCheckRecord.check_date <= end
        ).order_by(QualityCheckRecord.check_date).all()

        return {
            "success": True,
            "records": [
                {
                    "check_date": r.check_date.isoformat(),
                    "stock_count": r.stock_count,
                    "kline_covered": r.kline_covered,
                    "kline_missing": r.kline_missing,
                    "report_json": r.report_json,
                }
                for r in records
            ],
            "missing_dates": _get_missing_dates(session, start, end)
        }
    finally:
        session.close()


def _get_missing_dates(session, start, end) -> list:
    """获取区间内未检查的日期列表"""
    from common.models import QualityCheckRecord
    from datetime import timedelta

    checked = set(
        r.check_date for r in session.query(QualityCheckRecord.check_date).filter(
            QualityCheckRecord.check_date >= start,
            QualityCheckRecord.check_date <= end
        ).all()
    )

    missing = []
    current = start
    while current <= end:
        if current not in checked:
            missing.append(current.isoformat())
        current += timedelta(days=1)

    return missing


@app.post("/api/quality/check-range")
async def trigger_quality_check_range(start_date: str, end_date: str):
    """触发区间质量检查（执行检查并写入数据库）

    Args:
        start_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine
    from config import config
    from common.models import QualityCheckRecord
    from datetime import date, timedelta
    import json

    engine = create_engine(config.database.connection_url)
    session = Session(bind=engine)
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        # 获取已有记录的日期
        existing = set(
            r.check_date for r in session.query(QualityCheckRecord.check_date).filter(
                QualityCheckRecord.check_date >= start,
                QualityCheckRecord.check_date <= end
            ).all()
        )

        # 遍历每一天，跳过已检查的
        results = []
        checked_count = 0
        skipped_count = 0

        current = start
        while current <= end:
            if current in existing:
                skipped_count += 1
                current += timedelta(days=1)
                continue

            # 执行检查
            report = await _check_single_day(session, current)
            if report:
                # 存入数据库
                record = QualityCheckRecord(
                    check_date=current,
                    stock_count=report.get("stock_count", 0),
                    kline_covered=report.get("kline_covered", 0),
                    kline_missing=report.get("kline_missing", 0),
                    report_json=json.dumps(report, ensure_ascii=False)
                )
                session.add(record)
                results.append(report)
                checked_count += 1

            current += timedelta(days=1)

        session.commit()

        message = f"检查完成：{checked_count} 天新检查，{skipped_count} 天跳过（已有记录）"

        # 广播更新
        await manager.broadcast({
            "type": "quality_update",
            "message": message,
            "records": results
        })

        return {
            "success": True,
            "message": message,
            "checked_count": checked_count,
            "skipped_count": skipped_count,
            "results": results
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()


async def _check_single_day(session, check_date) -> dict:
    """检查单日数据质量"""
    from datetime import datetime
    from sqlalchemy import text

    try:
        # 检查股票数
        stock_count = session.execute(text("SELECT COUNT(*) FROM stock_basic")).scalar() or 0

        # 检查 K 线覆盖
        kline_result = session.execute(text("""
            SELECT COUNT(DISTINCT ts_code) as covered
            FROM stock_daily_kline
            WHERE trade_date = :check_date
        """), {"check_date": check_date}).fetchone()

        kline_covered = kline_result[0] if kline_result else 0
        kline_missing = stock_count - kline_covered

        return {
            "check_date": check_date.isoformat(),
            "stock_count": stock_count,
            "kline_covered": kline_covered,
            "kline_missing": kline_missing,
            "coverage_rate": round(kline_covered / stock_count * 100, 2) if stock_count > 0 else 0,
            "check_time": datetime.now().isoformat()
        }
    except Exception as e:
        logger.warning(f"质量检查失败 {check_date}: {e}")
        return None


# ==================== 采集后自动质量检查 (Q-6) ====================

async def trigger_quality_check_after_collect():
    """采集完成后自动触发质量检查"""
    from sqlalchemy.orm import Session
    from modules.collector.services.data_quality import QualityService
    from config import config

    try:
        from sqlalchemy import create_engine
        engine = create_engine(config.database.connection_url)
        session = Session(bind=engine)
        try:
            service = QualityService(session)
            results = service.check_all()
            service.save_report(results)

            # 广播质量更新通知
            await manager.broadcast({
                "type": "quality_update",
                "message": "质量检查已完成",
                "reports": [
                    {
                        "data_category": r["data_category"],
                        "total_score": r["total_score"],
                        "status": r["status"]
                    }
                    for r in results
                ]
            })
            logger.info("自动质量检查完成")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"自动质量检查失败: {e}")


def _save_concept_mapping(session, mapping: Dict[str, List[str]]) -> Dict[str, Any]:
    """保存概念板块映射到数据库

    Args:
        session: 数据库会话
        mapping: {concept_name: [symbol1, symbol2, ...]}

    Returns:
        {"concepts": N, "relations": N}
    """
    from models import Concept, StockConcept
    from sqlalchemy.dialects.mysql import insert as mysql_insert

    if not mapping:
        return {"concepts": 0, "relations": 0}

    # 1. UPSERT 概念板块表 (BUG-106)
    concept_id_map = {}
    for name, symbols in mapping.items():
        stmt = mysql_insert(Concept).values(
            name=name,
            block_type=0,
            stock_count=len(symbols)
        ).on_duplicate_key_update(
            stock_count=len(symbols)
        )
        session.execute(stmt)
    session.flush()  # 确保新插入的行对后续查询可见

    # 查询所有概念的 id（新插入 + 已存在）
    existing = session.query(Concept.id, Concept.name).filter(
        Concept.name.in_(list(mapping.keys()))
    ).all()
    for id_, name in existing:
        concept_id_map[name] = id_

    # 2. 全量刷新 stock_concept（先删后插）
    session.query(StockConcept).delete()

    batch_size = 5000
    relations = []
    for name, symbols in mapping.items():
        concept_id = concept_id_map.get(name)
        if concept_id is None:
            continue
        for symbol in symbols:
            relations.append({"symbol": symbol, "concept_id": concept_id})

    total_relations = len(relations)
    for i in range(0, total_relations, batch_size):
        batch = relations[i:i + batch_size]
        session.execute(StockConcept.__table__.insert().prefix_with("IGNORE"), batch)

    session.commit()
    logger.info(f"概念板块保存完成: {len(mapping)} 个概念, {total_relations} 条关联")

    return {"concepts": len(mapping), "relations": total_relations}


async def run_collect_concept():
    """后台运行：采集概念板块数据"""
    from sqlalchemy.orm import Session
    from sqlalchemy import create_engine
    from config import config
    from modules.collector.services.data_orchestrator import orchestrator

    try:
        await broadcast_status("progress", "开始采集概念板块数据...")

        loop = asyncio.get_running_loop()
        mapping = await loop.run_in_executor(
            None, orchestrator.collect_concept
        )

        if not mapping:
            await broadcast_status("error", "概念板块采集失败：无数据")
            logger.error("概念板块采集失败：无数据")
            return

        # 保存到数据库
        engine = create_engine(config.database.connection_url)
        session = Session(bind=engine)
        try:
            stats = await loop.run_in_executor(
                None, lambda: _save_concept_mapping(session, mapping)
            )
        finally:
            session.close()

        await broadcast_status("completed",
            f"概念板块采集完成: {stats['concepts']} 个概念, {stats['relations']} 条关联")
        logger.info(f"概念板块采集完成: {stats}")

    except Exception as e:
        logger.error(f"概念板块采集失败: {e}")
        await broadcast_status("error", f"概念板块采集失败: {e}")



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
        return {"success": True, "message": "无日志需要清理", "deleted_count": 0, "deleted_files": []}
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
    count = len(deleted)
    return {"success": True, "message": f"已清理 {count} 个日志文件", "deleted_count": count, "deleted_files": deleted, "cutoff_date": cutoff.isoformat()}


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

        # 批量查询概念板块（避免 N+1）
        symbols = [s.ts_code.split('.')[0] if s.ts_code else '' for s in stocks]
        concept_map = _batch_get_stock_concepts(session, [s for s in symbols if s])

        return {
            "total": total,
            "stocks": [
                {
                    "ts_code": s.ts_code,
                    "symbol": s.ts_code.split('.')[0] if s.ts_code else '',
                    "name": s.name,
                    "industry": s.industry,
                    "area": s.area,
                    "concepts": concept_map.get(s.ts_code.split('.')[0] if s.ts_code else '', [])
                }
                for s in stocks
            ]
        }
    finally:
        session.close()


@app.get("/api/stock/{symbol}/kline")
async def get_stock_kline(symbol: str, period: str = "day", limit: int = 200, end_date: Optional[str] = None):
    """获取个股K线数据（支持日/周/月/年周期切换）"""
    from modules.collector.services.data_orchestrator import orchestrator
    result = orchestrator.get_kline(
        symbol=symbol,
        period=period,
        limit=limit,
        end_date=end_date
    )
    return result


# ==================== 概念板块 API ====================

@app.get("/api/concepts")
async def get_concepts(search: Optional[str] = None, limit: int = 100):
    """获取概念板块列表（支持搜索）"""
    global collector
    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    from models import Concept
    session = Session(bind=collector.engine)
    try:
        query = session.query(Concept)

        # 搜索过滤
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(Concept.name.ilike(search_pattern))

        total = query.count()
        concepts = query.order_by(Concept.stock_count.desc()).limit(limit).all()

        return {
            "total": total,
            "concepts": [
                {
                    "id": c.id,
                    "name": c.name,
                    "block_type": c.block_type,
                    "stock_count": c.stock_count
                }
                for c in concepts
            ]
        }
    finally:
        session.close()


@app.get("/api/concepts/{concept_id}/stocks")
async def get_concept_stocks(concept_id: int, limit: int = 50, offset: int = 0):
    """获取指定概念板块下的所有股票"""
    global collector
    async with collector_lock:
        if collector is None:
            from main import StockDataCollector
            collector = StockDataCollector()

    from models import Concept, StockConcept, StockBasic
    session = Session(bind=collector.engine)
    try:
        concept = session.query(Concept).filter(Concept.id == concept_id).first()
        if not concept:
            return {"success": False, "message": "概念板块不存在"}

        query = session.query(StockBasic).join(
            StockConcept, StockBasic.symbol == StockConcept.symbol
        ).filter(StockConcept.concept_id == concept_id)

        total = query.count()
        stocks = query.limit(limit).offset(offset).all()

        # 批量查询概念板块（避免 N+1）
        symbols = [s.symbol for s in stocks if s.symbol]
        concept_map = _batch_get_stock_concepts(session, symbols)

        return {
            "success": True,
            "concept": {
                "id": concept.id,
                "name": concept.name,
                "stock_count": concept.stock_count
            },
            "total": total,
            "stocks": [
                {
                    "ts_code": s.ts_code,
                    "symbol": s.symbol,
                    "name": s.name,
                    "industry": s.industry,
                    "area": s.area,
                    "concepts": concept_map.get(s.symbol, [])
                }
                for s in stocks
            ]
        }
    finally:
        session.close()


@app.post("/api/collect/concept")
async def collect_concept(background_tasks: BackgroundTasks):
    """采集概念板块数据"""
    background_tasks.add_task(run_collect_concept)
    return {"success": True, "message": "概念板块采集任务已启动"}


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
    # 新客户端连接时发送当前状态，页面刷新后可恢复进度显示 (BUG-143)
    if task_status["running"]:
        completed = task_status.get("progress", 0)
        total = task_status.get("total", 0)
        percent = int(completed * 100 / total) if total > 0 else 0
        await websocket.send_json({
            "type": "progress",
            "completed": completed,
            "total": total,
            "percent": percent,
            "stats": task_status.get("stats"),
            "message": f"恢复进度: {completed}/{total} ({percent}%)"
        })
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
    def callback(completed, total, stats=None):
        # 检查是否请求停止
        if stop_requested.is_set():
            raise TaskStoppedException("用户请求停止任务")

        # 同步更新 task_status，确保 REST API 也能获取进度
        task_status["progress"] = completed
        task_status["total"] = total

        percent = int(completed * 100 / total) if total > 0 else 0
        if isinstance(stats, dict):
            records = stats.get('total_records', 0)
            msg = stats.get('message', f"进度: {completed}/{total} ({percent}%), 已采集 {records} 条")
        else:
            records = 0
            msg = stats or f"进度: {completed}/{total} ({percent}%)"

        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "progress",
                "completed": completed,
                "total": total,
                "percent": percent,
                "stats": stats,
                "message": msg
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

        percent = int(current * 100 / total) if total > 0 else 0
        # 同步更新 task_status，确保 REST API 也能获取进度
        task_status["progress"] = current
        task_status["total"] = total
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
        result = await loop.run_in_executor(
            None,
            lambda: collector.collect_stock_basic(
                progress_callback=progress_cb,
                stop_check=stop_requested.is_set
            )
        )

        if stop_requested.is_set():
            await broadcast_status("stopped", "任务已停止")
            return

        # 正确处理返回结果（修复 REG-003）
        # collect_stock_basic 返回字典 {"success": True, "total": N, "saved": N}
        saved_count = result.get("saved", 0) if isinstance(result, dict) else result
        total_count = result.get("total", saved_count) if isinstance(result, dict) else saved_count
        failed_count = total_count - saved_count
        stats = {
            "total": total_count,
            "saved": saved_count,
            "failed": failed_count,
            "success_rate": f"{saved_count * 100 / total_count:.1f}%" if total_count > 0 else "100%"
        }
        task_status["stats"] = _convert_numpy_types(stats)
        task_status["progress"] = saved_count
        task_status["total"] = saved_count
        await broadcast_status("completed", f"采集完成：成功 {saved_count} 条，失败 {failed_count} 条", stats)

    except TaskStoppedException:
        await broadcast_status("stopped", "任务已停止")
    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()
        # 采集完成后自动触发质量检查 (Q-6)
        await trigger_quality_check_after_collect()
        # 基础采集完成后自动触发概念板块采集 (BUG-106)
        await run_collect_concept()


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

        # 构建详细统计信息
        success_count = stats.get("success_count", 0)
        failed_count = stats.get("failed_count", 0)
        total_count = stats.get("total", success_count + failed_count)
        total_records = stats.get("total_records", 0)
        collect_stats = {
            "total_stocks": total_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "total_records": total_records,
            "success_rate": f"{success_count * 100 / total_count:.1f}%" if total_count > 0 else "100%"
        }
        task_status["stats"] = _convert_numpy_types(collect_stats)
        task_status["progress"] = stats.get("total", 0)
        task_status["total"] = stats.get("total", 0)
        await broadcast_status("completed",
            f"K线采集完成：成功 {success_count} 只，失败 {failed_count} 只，共 {total_records} 条记录",
            collect_stats)

    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()
        # 采集完成后自动触发质量检查 (Q-6)
        await trigger_quality_check_after_collect()


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
        # 构建详细统计信息
        success_count = stats.get("success_count", 0)
        failed_count = stats.get("failed_count", 0)
        total_count = stats.get("total", success_count + failed_count)
        total_records = stats.get("total_records", 0)
        collect_stats = {
            "total_stocks": total_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "total_records": total_records,
            "success_rate": f"{success_count * 100 / total_count:.1f}%" if total_count > 0 else "100%"
        }
        await broadcast_status("completed",
            f"增量采集完成：成功 {success_count} 只，失败 {failed_count} 只，共 {total_records} 条记录",
            collect_stats)

    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()
        # 采集完成后自动触发质量检查 (Q-6)
        await trigger_quality_check_after_collect()


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

        # 构建详细统计信息
        total_count = stats.get("total", 0)
        saved_count = stats.get("saved", total_count)
        failed_count = total_count - saved_count
        collect_stats = {
            "total_quotes": total_count,
            "saved_count": saved_count,
            "failed_count": failed_count,
            "success_rate": f"{saved_count * 100 / total_count:.1f}%" if total_count > 0 else "100%"
        }
        task_status["stats"] = _convert_numpy_types(collect_stats)
        task_status["progress"] = stats.get("total", 0)
        task_status["total"] = stats.get("total", 0)
        await broadcast_status("completed",
            f"实时行情采集完成：成功 {saved_count} 条，失败 {failed_count} 条",
            collect_stats)

    except Exception as e:
        task_status["error"] = str(e)
        await broadcast_status("error", str(e))
    finally:
        async with task_lock:
            task_status["running"] = False
            stop_requested.clear()
        # 采集完成后自动触发质量检查 (Q-6)
        await trigger_quality_check_after_collect()


# ==================== 辅助函数 ====================

async def broadcast_status(status_type: str, message: str, stats: dict = None):
    """广播状态更新"""
    payload = {
        "type": status_type,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    if stats:
        payload["stats"] = stats
    await manager.broadcast(payload)



# ==================== GitHub Project 同步 API ====================

@app.get("/api/github/sync-status")
async def get_github_sync_status():
    """获取 GitHub Project 同步状态"""
    import subprocess

    # 检查最近提交是否包含 Issue 编号
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent)
        )
        commit_msg = result.stdout.strip()
        issue_nums = re.findall(r'#(\d+)', commit_msg)

        return {
            "last_commit": commit_msg,
            "linked_issues": issue_nums,
            "sync_available": len(issue_nums) > 0
        }
    except Exception as e:
        return {
            "last_commit": "",
            "linked_issues": [],
            "sync_available": False,
            "error": str(e)
        }


@app.post("/api/github/sync")
async def trigger_github_sync():
    """触发 GitHub Project 同步"""
    import subprocess

    script_path = Path(__file__).parent / "scripts" / "sync-project.sh"
    if not script_path.exists():
        return {"success": False, "message": "同步脚本不存在"}

    try:
        result = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).parent)
        )
        return {
            "success": True,
            "message": "同步完成",
            "output": result.stdout,
            "errors": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "同步超时"}
    except Exception as e:
        return {"success": False, "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)