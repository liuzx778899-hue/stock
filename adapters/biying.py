"""
必盈 API 数据源适配器

自包含模块：内部管理 BiyingAPIAdapter、BiyingLicencePool、Licence 数据库持久化。
文档: https://www.biyingapi.com/doc_hs
"""
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

import pandas as pd
import requests
from sqlalchemy import create_engine, select, update, delete
from sqlalchemy.orm import sessionmaker

from adapters.base import DataProvider, DataCategory, ProviderCapability
from config import config
from models import BiyingLicence
from utils import logger


# ==================== Licence 数据库持久化 ====================

class BiyingLicenceStore:
    """必盈 Licence 数据库存储管理器"""

    def __init__(self):
        self.engine = create_engine(
            config.database.connection_url,
            pool_size=5, max_overflow=10, pool_pre_ping=True,
        )
        self.Session = sessionmaker(bind=self.engine)
        self._ensure_table()

    def _ensure_table(self):
        try:
            from models import Base
            Base.metadata.create_all(self.engine, tables=[BiyingLicence.__table__])
        except Exception as e:
            logger.warning(f"创建 biying_licence 表失败: {e}")

    def load_licences(self) -> List[str]:
        """从数据库加载所有 Licence"""
        session = self.Session()
        try:
            results = session.execute(
                select(BiyingLicence.licence).order_by(BiyingLicence.id)
            ).scalars().all()
            return list(results)
        except Exception:
            return []
        finally:
            session.close()

    def add_licence(self, licence: str) -> bool:
        """添加单个 Licence"""
        session = self.Session()
        try:
            existing = session.execute(
                select(BiyingLicence).where(BiyingLicence.licence == licence)
            ).scalar_one_or_none()
            if existing:
                return False
            count = session.execute(select(BiyingLicence.id)).scalars().all()
            new_lic = BiyingLicence(
                licence=licence,
                is_current=1 if len(count) == 0 else 0,
                is_available=1,
            )
            session.add(new_lic)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"添加 Licence 失败: {e}")
            return False
        finally:
            session.close()

    def remove_licence(self, licence: str) -> bool:
        """从数据库移除 Licence"""
        session = self.Session()
        try:
            result = session.execute(
                delete(BiyingLicence).where(BiyingLicence.licence == licence)
            )
            session.commit()
            return result.rowcount > 0
        except Exception as e:
            session.rollback()
            logger.error(f"移除 Licence 失败: {e}")
            return False
        finally:
            session.close()

    def get_status(self) -> List[dict]:
        """获取所有 Licence 状态"""
        session = self.Session()
        try:
            results = session.execute(
                select(BiyingLicence).order_by(BiyingLicence.id)
            ).scalars().all()
            return [
                {
                    'licence': (lic.licence[:8] + '...' + lic.licence[-4:]
                                if len(lic.licence) > 12 else lic.licence),
                    'full_licence': lic.licence,
                    'usage_count': lic.usage_count,
                    'error_count': lic.error_count,
                    'is_current': bool(lic.is_current),
                    'is_available': bool(lic.is_available),
                }
                for lic in results
            ]
        except Exception:
            return []
        finally:
            session.close()

    def update_usage(self, licence: str, success: bool):
        """更新 Licence 使用状态"""
        session = self.Session()
        try:
            if success:
                session.execute(
                    update(BiyingLicence)
                    .where(BiyingLicence.licence == licence)
                    .values(
                        usage_count=BiyingLicence.usage_count + 1,
                        error_count=0, is_available=1,
                    )
                )
            else:
                session.execute(
                    update(BiyingLicence)
                    .where(BiyingLicence.licence == licence)
                    .values(error_count=BiyingLicence.error_count + 1)
                )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"更新 Licence 状态失败: {e}")
        finally:
            session.close()

    def set_current(self, licence: str):
        """设置当前使用的 Licence"""
        session = self.Session()
        try:
            session.execute(update(BiyingLicence).values(is_current=0))
            session.execute(
                update(BiyingLicence)
                .where(BiyingLicence.licence == licence)
                .values(is_current=1)
            )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"设置当前 Licence 失败: {e}")
        finally:
            session.close()

    def reset_errors(self):
        """重置所有 Licence 的错误计数"""
        session = self.Session()
        try:
            session.execute(
                update(BiyingLicence).values(error_count=0, is_available=1)
            )
            session.commit()
        except Exception as e:
            session.rollback()
        finally:
            session.close()


# ==================== Licence 池管理器 ====================

class BiyingLicencePool:
    """Licence 池管理器（数据库持久化）"""

    def __init__(self, licences: Optional[List[str]] = None):
        self.store = BiyingLicenceStore()
        self.licences: List[str] = licences if licences is not None else []
        self.current_index = 0
        self.max_errors = 3

        # 如果没传 licences，从数据库加载
        if not self.licences:
            self.licences = self.store.load_licences()

    def add_licence(self, licence: str):
        if licence not in self.licences:
            self.licences.append(licence)
            self.store.add_licence(licence)
            logger.info(f"添加新 Licence: {licence[:8]}...")

    def remove_licence(self, licence: str):
        if licence in self.licences:
            self.licences.remove(licence)
            self.store.remove_licence(licence)
            logger.info(f"移除 Licence: {licence[:8]}...")

    def get_current(self) -> Optional[str]:
        if not self.licences:
            return None
        return self.licences[self.current_index]

    def switch_next(self) -> Optional[str]:
        """切换到下一个可用的 Licence"""
        if not self.licences:
            return None

        status = self.store.get_status()
        status_map = {s['full_licence']: s for s in status}

        start = self.current_index
        for i in range(len(self.licences)):
            idx = (start + i + 1) % len(self.licences)
            lic = self.licences[idx]
            lic_status = status_map.get(lic, {})
            if lic_status.get('error_count', 0) < self.max_errors:
                self.current_index = idx
                self.store.set_current(lic)
                logger.info(f"切换 Licence: {lic[:8]}...")
                return lic

        logger.warning("所有 Licence 都达到错误上限，重置错误计数")
        self.store.reset_errors()
        self.current_index = 0
        return self.licences[0]

    def record_success(self, licence: str):
        self.store.update_usage(licence, success=True)

    def record_error(self, licence: str):
        self.store.update_usage(licence, success=False)

    def get_status(self) -> List[Dict]:
        return self.store.get_status()


# ==================== API 适配器 ====================

class BiyingAPIAdapter:
    """必盈 HTTP API 适配器"""

    BASE_URL = "https://api.biyingapi.com"

    def __init__(self, licences: Optional[List[str]] = None):
        self.licence_pool = BiyingLicencePool(licences)
        self.timeout = 30

    # ---- Licence 管理 ----

    def add_licence(self, licence: str):
        self.licence_pool.add_licence(licence)

    def remove_licence(self, licence: str):
        self.licence_pool.remove_licence(licence)

    def get_licence_status(self) -> List[Dict]:
        return self.licence_pool.get_status()

    # ---- HTTP 请求 ----

    def _build_url(self, endpoint: str, licence: Optional[str] = None,
                   code: Optional[str] = None) -> str:
        lic = licence or self.licence_pool.get_current()
        if not lic:
            raise ValueError("没有可用的 Licence")
        if code:
            return f"{self.BASE_URL}/{endpoint}/{code}/{lic}"
        return f"{self.BASE_URL}/{endpoint}/{lic}"

    def _request(self, endpoint: str, code: Optional[str] = None,
                 retry_on_error: bool = True) -> Optional[Any]:
        max_attempts = len(self.licence_pool.licences) if retry_on_error else 1
        for attempt in range(max_attempts):
            licence = self.licence_pool.get_current()
            if not licence:
                return None
            url = self._build_url(endpoint, licence, code)
            try:
                resp = requests.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    self.licence_pool.record_success(licence)
                    return data
                elif resp.status_code == 429 or 'quota' in resp.text.lower():
                    logger.warning(f"Licence {licence[:8]}... 配额用完，切换下一个")
                    self.licence_pool.switch_next()
                else:
                    self.licence_pool.record_error(licence)
                    if retry_on_error:
                        self.licence_pool.switch_next()
            except Exception as e:
                self.licence_pool.record_error(licence)
                if retry_on_error:
                    self.licence_pool.switch_next()
        return None

    # ---- 股票基础信息 ----

    def get_stock_list(self) -> pd.DataFrame:
        data = self._request("hslt/list")
        if data:
            df = pd.DataFrame(data)
            df = df.rename(columns={'dm': '代码', 'mc': '名称', 'jys': '交易所'})
            return df
        return pd.DataFrame()

    def get_stock_info(self, code: str) -> Optional[Dict]:
        data = self._request("hscp/gsjj", code=code)
        if data:
            return {
                '代码': code,
                '名称': data.get('gsmc', data.get('name', '')),
                '行业': data.get('sshy', data.get('industry', '')),
                '地区': data.get('ssdq', data.get('area', '')),
                '上市日期': data.get('ssrq', data.get('list_date', '')),
                '总股本': data.get('zgb', data.get('total_share', 0)),
                '流通股本': data.get('ltgb', data.get('float_share', 0)),
            }
        return None

    def get_industry_area_mapping(self) -> tuple:
        """获取所有股票的行业和地区映射"""
        industry_map = {}
        area_map = {}
        df_list = self.get_stock_list()
        if df_list.empty:
            return {}, {}

        logger.info(f"必盈API 开始获取 {len(df_list)} 只股票的行业/地区信息...")
        for i, (_, row) in enumerate(df_list.iterrows()):
            code = row['代码']
            try:
                info = self.get_stock_info(code)
                if info:
                    if info.get('行业'):
                        industry_map[code] = info['行业']
                    if info.get('地区'):
                        area_map[code] = info['地区']
                if (i + 1) % 100 == 0:
                    logger.info(f"已获取 {i+1}/{len(df_list)} 只股票的行业/地区")
                time.sleep(0.05)
            except Exception:
                continue

        logger.info(f"必盈API 完成: {len(industry_map)} 行业, {len(area_map)} 地区")
        return industry_map, area_map

    # ---- 实时行情 ----

    def get_stock_realtime(self, code: str) -> Optional[Dict]:
        data = self._request("hsstock/real/time", code=code)
        if data:
            return {
                '代码': code, '名称': '',
                '现价': data.get('p', 0), '开盘': data.get('o', 0),
                '最高': data.get('h', 0), '最低': data.get('l', 0),
                '昨收': data.get('yc', 0), '涨跌幅': data.get('pc', 0) * 100,
                '换手率': data.get('tr', 0), '成交量': data.get('v', 0),
                '成交额': data.get('cje', 0),
                '时间': data.get('t', ''),
            }
        return None

    # ---- 历史K线 ----

    def get_history_kline(self, code: str, start_date: Optional[str] = None,
                          end_date: Optional[str] = None, period: str = 'd',
                          adjust: str = 'n') -> pd.DataFrame:
        endpoint = f"hsstock/history/kline/{period}/{adjust}"
        if start_date and end_date:
            endpoint += f"?st={start_date}&et={end_date}"
        data = self._request(endpoint, code=code)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()


# ==================== 全局适配器实例 ====================

_biying_adapter: Optional[BiyingAPIAdapter] = None


def get_biying_adapter() -> Optional[BiyingAPIAdapter]:
    """获取必盈 API 适配器实例"""
    global _biying_adapter
    return _biying_adapter


def init_biying_adapter(licences: Optional[List[str]] = None,
                        licence: Optional[str] = None) -> BiyingAPIAdapter:
    """初始化必盈 API 适配器"""
    global _biying_adapter
    if not licences and not licence:
        licences = BiyingLicenceStore().load_licences()
    _biying_adapter = BiyingAPIAdapter(licences=licences)
    # 如果传了单个 licence，添加到池中
    if licence and licence not in (_biying_adapter.licence_pool.licences or []):
        _biying_adapter.add_licence(licence)
    logger.info(f"必盈 API 适配器初始化完成，Licence 数量: "
                f"{len(_biying_adapter.licence_pool.licences)}")
    return _biying_adapter


def add_biying_licence(licence: str):
    global _biying_adapter
    if _biying_adapter is None:
        init_biying_adapter(licence=licence)
    else:
        _biying_adapter.add_licence(licence)


def remove_biying_licence(licence: str):
    global _biying_adapter
    if _biying_adapter:
        _biying_adapter.remove_licence(licence)


def get_biying_status() -> List[Dict]:
    global _biying_adapter
    if _biying_adapter:
        return _biying_adapter.get_licence_status()
    return BiyingLicenceStore().get_status()


# ==================== DataProvider 实现 ====================

class BiyingProvider(DataProvider):
    """必盈数据源提供者（付费 API）"""

    @property
    def provider_name(self) -> str:
        return "biying"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.STOCK_BASIC,
                fields=["symbol", "name", "exchange"],
                quality_score=0.85, cost_type="paid", latency_ms=200,
            ),
            ProviderCapability(
                category=DataCategory.STOCK_INDUSTRY,
                fields=["symbol", "industry_name"],
                quality_score=0.9, cost_type="paid", latency_ms=100,
            ),
            ProviderCapability(
                category=DataCategory.STOCK_AREA,
                fields=["symbol", "area_name"],
                quality_score=0.9, cost_type="paid", latency_ms=100,
            ),
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["open", "high", "low", "close", "volume", "amount",
                        "pct_chg", "turnover_rate"],
                quality_score=0.9, cost_type="paid", latency_ms=150,
            ),
            ProviderCapability(
                category=DataCategory.REALTIME_QUOTE,
                fields=["symbol", "name", "price", "open", "high", "low",
                        "pre_close", "volume", "amount", "pct_chg", "turnover_rate"],
                quality_score=0.85, cost_type="paid", latency_ms=80,
            ),
        ]

    def _get_adapter(self) -> Optional[BiyingAPIAdapter]:
        adapter = get_biying_adapter()
        if adapter is None:
            init_biying_adapter()
            adapter = get_biying_adapter()
        return adapter

    # ---- 数据获取方法 ----

    def fetch_stock_basic(self) -> pd.DataFrame:
        adapter = self._get_adapter()
        if adapter is None:
            return pd.DataFrame()
        return adapter.get_stock_list()

    def fetch_industry_mapping(self) -> Dict[str, str]:
        adapter = self._get_adapter()
        if adapter is None:
            return {}
        industry_map, _ = adapter.get_industry_area_mapping()
        return industry_map

    def fetch_area_mapping(self) -> Dict[str, str]:
        adapter = self._get_adapter()
        if adapter is None:
            return {}
        _, area_map = adapter.get_industry_area_mapping()
        return area_map

    def fetch_kline(self, symbol: str, start_date: str, end_date: str,
                    adjust: str = "qfq") -> pd.DataFrame:
        adapter = self._get_adapter()
        if adapter is None:
            return pd.DataFrame()
        biying_adj = adjust if adjust in ('qfq', 'hfq', 'n') else 'n'
        return adapter.get_history_kline(symbol, start_date, end_date,
                                         period='d', adjust=biying_adj)

    def fetch_realtime(self, symbol: Optional[str] = None) -> pd.DataFrame:
        adapter = self._get_adapter()
        if adapter is None:
            return pd.DataFrame()
        if symbol:
            data = adapter.get_stock_realtime(symbol)
            return pd.DataFrame([data]) if data else pd.DataFrame()
        # 全量
        df_list = adapter.get_stock_list()
        if df_list.empty:
            return pd.DataFrame()
        results = []
        for _, row in df_list.iterrows():
            rt = adapter.get_stock_realtime(row['代码'])
            if rt:
                results.append(rt)
            time.sleep(0.02)
        return pd.DataFrame(results) if results else pd.DataFrame()

    # ---- Licence 管理代理方法 ----

    def add_licence(self, licence: str):
        adapter = self._get_adapter()
        if adapter:
            adapter.add_licence(licence)

    def remove_licence(self, licence: str):
        adapter = self._get_adapter()
        if adapter:
            adapter.remove_licence(licence)

    def get_licence_status(self) -> List[Dict]:
        adapter = self._get_adapter()
        if adapter:
            return adapter.get_licence_status()
        return BiyingLicenceStore().get_status()

    def health_check(self) -> bool:
        adapter = self._get_adapter()
        if adapter is None:
            return False
        try:
            df = adapter.get_stock_list()
            return not df.empty
        except Exception:
            return False
