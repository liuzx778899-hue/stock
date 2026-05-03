"""
通达信数据源适配器（mootdx TCP 协议）

通过 TCP 协议绕过 HTTP 代理，获取行业/地区分类数据。
使用 mootdx F10 接口 + 多线程加速 + 本地缓存。
"""
from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pandas as pd

from adapters.base import DataProvider, DataCategory, ProviderCapability
from utils import logger


# 省份/直辖市列表（用于从地址提取地区）
PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "广东", "浙江", "江苏", "山东", "河南", "四川",
    "湖北", "湖南", "福建", "安徽", "河北", "辽宁", "陕西",
    "江西", "广西", "山西", "云南", "贵州", "内蒙古",
    "吉林", "甘肃", "新疆", "海南", "宁夏", "青海", "西藏", "黑龙江",
]


class TdxProvider(DataProvider):
    """通达信数据源适配器（mootdx TCP 协议）

    提供行业/地区分类数据，通过 F10 接口逐只获取。
    使用多线程加速 + 本地缓存。

    不提供股票列表、K线、实时行情（保持现有数据源）。
    """

    # 线程安全的 Quotes 管理
    _local: threading.local = threading.local()
    _quotes_instance: Any = None  # 主线程共享实例（用于单只查询）

    # 缓存文件路径
    CACHE_FILE = "mootdx_cache.json"
    CACHE_TTL_HOURS = 24

    def __init__(self):
        self._cache_data: Dict[str, Any] = {}
        self._cache_loaded = False

    @property
    def provider_name(self) -> str:
        return "mootdx"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.STOCK_INDUSTRY,
                fields=["symbol", "industry_name"],
                quality_score=0.8,
                cost_type="free",
                latency_ms=1000,  # F10 查询约 1 秒
            ),
            ProviderCapability(
                category=DataCategory.STOCK_AREA,
                fields=["symbol", "area_name"],
                quality_score=0.7,
                cost_type="free",
                latency_ms=1000,
            ),
        ]

    @property
    def field_mapping(self) -> Dict[DataCategory, Dict[str, str]]:
        # mootdx 返回的数据直接使用标准字段名，无需映射
        return {}

    # ---- Quotes 连接管理（线程安全）----

    @property
    def _quotes(self):
        """获取 Quotes 实例（主线程共享）"""
        if self._quotes_instance is None:
            try:
                from mootdx.quotes import Quotes
                self._quotes_instance = Quotes.factory(market='std')
                logger.info(f"[mootdx] TCP 连接成功（标准市场）")
            except Exception as e:
                logger.error(f"[mootdx] TCP 连接失败: {e}")
                return None
        return self._quotes_instance

    def _get_thread_quotes(self):
        """获取线程本地 Quotes 实例（多线程场景）"""
        if not hasattr(self._local, 'quotes'):
            try:
                from mootdx.quotes import Quotes
                self._local.quotes = Quotes.factory(market='std')
            except Exception as e:
                logger.warning(f"[mootdx] 线程 TCP 连接失败: {e}")
                return None
        return self._local.quotes

    # ---- 缓存层 ----

    def _load_cache(self) -> Dict[str, Any]:
        """加载缓存文件"""
        if self._cache_loaded:
            return self._cache_data

        cache_path = self._get_cache_path()
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 检查 TTL
                updated_at = data.get("updated_at")
                if updated_at:
                    cache_time = datetime.fromisoformat(updated_at)
                    if datetime.now() - cache_time < timedelta(hours=self.CACHE_TTL_HOURS):
                        self._cache_data = data
                        self._cache_loaded = True
                        logger.info(f"[mootdx] 缓存命中，行业 {len(data.get('industry', {}))} 条，地区 {len(data.get('area', {}))} 条")
                        return self._cache_data
                    else:
                        logger.info(f"[mootdx] 缓存过期（>{self.CACHE_TTL_HOURS}h），重新获取")
            except Exception as e:
                logger.warning(f"[mootdx] 缓存加载失败: {e}")

        self._cache_data = {"industry": {}, "area": {}, "updated_at": None}
        return self._cache_data

    def _save_cache(self):
        """保存缓存文件"""
        cache_path = self._get_cache_path()
        self._cache_data["updated_at"] = datetime.now().isoformat()
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache_data, f, ensure_ascii=False, indent=2)
            logger.info(f"[mootdx] 缓存已保存: {cache_path}")
        except Exception as e:
            logger.warning(f"[mootdx] 缓存保存失败: {e}")

    def _get_cache_path(self) -> str:
        """获取缓存文件绝对路径"""
        # 放在项目根目录
        from config import BASE_DIR
        return os.path.join(BASE_DIR, self.CACHE_FILE)

    # ---- F10 解析 ----

    def _parse_industry(self, f10_data: dict) -> Optional[str]:
        """从 F10 数据提取行业分类

        原始格式：
        【所属行业】
        ----股份制银行Ⅱ--股份制银行Ⅱ(9)

        提取规则：匹配 `----xxx--xxx(N)` 模式，取最后一段
        """
        if not f10_data:
            return None

        hyfx = f10_data.get("行业分析", "")
        if not hyfx:
            return None

        # 匹配: ----行业名称--行业名称(N)
        # 使用反向引用确保两个行业名称相同
        pattern = r'--+([^-]+)--+\1\(\d+\)'
        match = re.search(pattern, hyfx)
        if match:
            industry = match.group(1).strip()
            # 清理可能的乱码/后缀
            industry = re.sub(r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$', '', industry).strip()
            return industry if industry else None

        # 备用正则（宽松匹配）
        pattern2 = r'--+([^-]+)--\S*\(\d+\)'
        match2 = re.search(pattern2, hyfx)
        if match2:
            industry = match2.group(1).strip()
            industry = re.sub(r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$', '', industry).strip()
            return industry if industry else None
        return None

    def _parse_area(self, f10_data: dict) -> Optional[str]:
        """从 F10 数据提取地区（省份/直辖市）

        原始格式：
        【公司资料】
        注册地址: 深圳市罗湖区...
        """
        if not f10_data:
            return None

        gsgk = f10_data.get("公司概况", "")
        if not gsgk:
            return None

        # 优先匹配注册地址/办公地址行
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

    # ---- F10 批量查询 ----

    def _fix_encoding(self, text: str) -> str:
        """修复 mootdx F10 数据的编码问题

        mootdx 内部可能将 GBK 数据误解码，
        导致中文显示为乱码。尝试转回 GBK。
        """
        if not text or not isinstance(text, str):
            return text
        try:
            # 检测是否包含中文，如果有则不需要修复
            if any('一' <= c <= '鿿' for c in text):
                return text

            # 检测是否为乱码：包含非 ASCII 且非中文的字符
            has_garbled = any(ord(c) > 127 and not ('一' <= c <= '鿿') for c in text)
            if not has_garbled:
                return text

            # 尝试多种编码修复路径
            # 路径1: Unicode code points → GBK bytes → decode as GBK
            try:
                # 将 Unicode 字符转为原始字节（假设每个字符是一个字节）
                raw_bytes = bytes([ord(c) for c in text if ord(c) < 256])
                if raw_bytes:
                    return raw_bytes.decode('gbk', errors='ignore')
            except Exception:
                pass

            # 路径2: encode as cp1252 → decode as gbk
            try:
                return text.encode('cp1252', errors='ignore').decode('gbk', errors='ignore')
            except Exception:
                pass

            return text
        except Exception:
            return text

    def _fix_f10_encoding(self, data: dict) -> dict:
        """修复 F10 dict 的编码问题"""
        if not data:
            return data
        fixed = {}
        for key, value in data.items():
            fixed_key = self._fix_encoding(key)
            if isinstance(value, str):
                fixed[fixed_key] = self._fix_encoding(value)
            else:
                fixed[fixed_key] = value
        return fixed

    def _fetch_one_f10(self, symbol: str, use_thread_quotes: bool = False) -> Optional[dict]:
        """获取单只股票的 F10 数据"""
        quotes = self._get_thread_quotes() if use_thread_quotes else self._quotes
        if quotes is None:
            return None

        try:
            # 去除 bj/sh/sz 等前缀，标准化为 6 位代码
            code = symbol.replace('bj', '').replace('sh', '').replace('sz', '').zfill(6)
            data = quotes.F10(code)
            # 修复编码问题 (BUG-095)
            return self._fix_f10_encoding(data)
        except Exception as e:
            logger.warning(f"[mootdx] F10 获取失败 {symbol}: {e}")
            return None

    def _batch_fetch_f10(self, symbols: List[str]) -> Dict[str, dict]:
        """多线程批量获取 F10 数据（16 线程）"""
        results = {}
        total = len(symbols)
        success = 0
        failed = 0

        logger.info(f"[mootdx] 开始批量 F10 查询，{total} 只股票，16 线程...")

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(self._fetch_one_f10, s, True): s for s in symbols}
            for i, future in enumerate(as_completed(futures), 1):
                symbol = futures[future]
                try:
                    data = future.result()
                    if data:
                        results[symbol] = data
                        success += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.warning(f"[mootdx] F10 异常 {symbol}: {e}")
                    failed += 1

                # 进度日志（每 500 只）
                if i % 500 == 0 or i == total:
                    logger.info(f"[mootdx] F10 进度: {i}/{total}，成功 {success}，失败 {failed}")

        logger.info(f"[mootdx] F10 查询完成: 成功 {success}，失败 {failed}")
        return results

    # ---- 北交所后备方案（技术方案 3.2）----

    def _fetch_bse_mapping(self) -> tuple[Dict[str, str], Dict[str, str]]:
        """从 AkShare 获取北交所行业和地区映射

        mootdx F10 不支持北交所代码（8/92xxxx），使用 AkShare BSE API 作为后备。
        该接口调用东方财富 BSE 专用端点，未被代理拦截。

        Returns:
            (industry_mapping, area_mapping) 两个字典
        """
        try:
            import akshare as ak
            df = ak.stock_info_bj_name_code()

            industry_map = {}
            area_map = {}

            for _, row in df.iterrows():
                code = str(row.get('证券代码', row.get('代码', ''))).zfill(6)
                industry = str(row.get('所属行业', row.get('行业', '')))
                # 省份可能在不同列名下
                area = str(row.get('省份', row.get('地区', '')))

                if code:
                    # 同时返回带 bj 前缀和不带前缀的格式，兼容数据库中的两种情况
                    if industry and industry != 'nan':
                        industry_map[code] = industry          # 不带前缀: 920000
                        industry_map[f'bj{code}'] = industry  # 带 bj 前缀: bj920000
                    if area and area != 'nan':
                        area_map[code] = area
                        area_map[f'bj{code}'] = area

            logger.info(f"[mootdx] BSE API 获取: 行业 {len(industry_map)} 条, 地区 {len(area_map)} 条")
            return industry_map, area_map
        except Exception as e:
            logger.warning(f"[mootdx] BSE API 获取失败: {e}")
            return {}, {}

    def _is_bse_symbol(self, symbol: str) -> bool:
        """判断是否为北交所代码

        北交所代码前缀: 83, 87, 92, 93 (北交所专用代码段)
        支持 bj 前缀格式：bj920000 → 920000
        """
        if not symbol:
            return False
        # 去除 bj/sh/sz 等前缀（支持大小写）
        code = symbol.lower().replace('bj', '').replace('sh', '').replace('sz', '').strip()
        # 确保是6位数字格式
        code = code.zfill(6)
        return code.startswith(('83', '87', '92', '93'))

    def _is_hs_symbol(self, symbol: str) -> bool:
        """判断是否为沪深代码

        沪深代码前缀: 60, 00, 30, 68 (上证、深证、创业板、科创板)
        支持 sh/sz 前缀格式：sh600000 → 600000
        """
        if not symbol:
            return False
        # 去除 bj/sh/sz 等前缀（支持大小写）
        code = symbol.lower().replace('bj', '').replace('sh', '').replace('sz', '').strip()
        # 确保是6位数字格式
        code = code.zfill(6)
        return code.startswith(('60', '00', '30', '68'))

    # ---- DataProvider 接口实现 ----

    def fetch_industry_mapping(self, symbols: Optional[List[str]] = None) -> Dict[str, str]:
        """返回 {symbol: industry_name} 映射

        内部自动分流：
        - 沪深代码 → mootdx F10 (TCP)
        - 北交所代码 → AkShare BSE API (HTTP)

        Args:
            symbols: 可选的股票代码列表。传入时直接从该列表获取股票，
                     不查数据库（用于首次采集时 DB 为空的情况）。
        """
        cache = self._load_cache()
        cached_industry = cache.get("industry", {})

        # 如果缓存有数据且未过期，直接返回
        if cached_industry and cache.get("updated_at"):
            return cached_industry

        # 获取股票列表：优先使用传入的 symbols，否则从数据库查询
        if symbols is not None:
            all_symbols = symbols
        else:
            from sqlalchemy.orm import Session as ORMSession
            from config import config
            from sqlalchemy import create_engine
            from models import StockBasic
            try:
                engine = create_engine(config.database.connection_url)
                with ORMSession(bind=engine) as session:
                    stocks = session.query(StockBasic.symbol).all()
                    all_symbols = [s.symbol for s in stocks]
            except Exception as e:
                logger.error(f"[mootdx] 获取股票列表失败: {e}")
                return cached_industry

        # 找出需要查询的股票（缓存缺失）
        need_fetch = [s for s in all_symbols if s not in cached_industry]
        if not need_fetch:
            logger.info("[mootdx] 行业缓存完整，无需重新获取")
            return cached_industry

        logger.info(f"[mootdx] 需获取 {len(need_fetch)} 只股票的行业信息...")

        # 分流：沪深 vs 北交所
        hs_symbols = [s for s in need_fetch if self._is_hs_symbol(s)]
        bse_symbols = [s for s in need_fetch if self._is_bse_symbol(s)]

        new_industry = {}

        # 沪深股票：mootdx F10
        if hs_symbols:
            logger.info(f"[mootdx] 沪深股票 {len(hs_symbols)} 只，使用 F10 查询...")
            f10_data = self._batch_fetch_f10(hs_symbols)
            for symbol, data in f10_data.items():
                industry = self._parse_industry(data)
                if industry:
                    new_industry[symbol] = industry

        # 北交所股票：AkShare BSE API
        if bse_symbols:
            logger.info(f"[mootdx] 北交所股票 {len(bse_symbols)} 只，使用 BSE API 查询...")
            bse_industry, _ = self._fetch_bse_mapping()
            for symbol in bse_symbols:
                if symbol in bse_industry:
                    new_industry[symbol] = bse_industry[symbol]

        # 合并缓存
        self._cache_data["industry"] = {**cached_industry, **new_industry}
        self._save_cache()

        coverage = len(self._cache_data["industry"]) / len(all_symbols) * 100 if all_symbols else 0
        logger.info(f"[mootdx] 行业覆盖率: {coverage:.1f}% ({len(self._cache_data['industry'])}/{len(all_symbols)})")

        return self._cache_data["industry"]

    def fetch_area_mapping(self, symbols: Optional[List[str]] = None) -> Dict[str, str]:
        """返回 {symbol: area_name} 映射

        内部自动分流：
        - 沪深代码 → mootdx F10 (TCP)
        - 北交所代码 → AkShare BSE API (HTTP)

        Args:
            symbols: 可选的股票代码列表。传入时直接从该列表获取股票，
                     不查数据库（用于首次采集时 DB 为空的情况）。
        """
        cache = self._load_cache()
        cached_area = cache.get("area", {})

        # 如果缓存有数据且未过期，直接返回
        if cached_area and cache.get("updated_at"):
            return cached_area

        # 获取股票列表：优先使用传入的 symbols，否则从数据库查询
        if symbols is not None:
            all_symbols = symbols
        else:
            from sqlalchemy.orm import Session as ORMSession
            from config import config
            from sqlalchemy import create_engine
            from models import StockBasic
            try:
                engine = create_engine(config.database.connection_url)
                with ORMSession(bind=engine) as session:
                    stocks = session.query(StockBasic.symbol).all()
                    all_symbols = [s.symbol for s in stocks]
            except Exception as e:
                logger.error(f"[mootdx] 获取股票列表失败: {e}")
                return cached_area

        # 找出需要查询的股票（缓存缺失）
        need_fetch = [s for s in all_symbols if s not in cached_area]
        if not need_fetch:
            logger.info("[mootdx] 地区缓存完整，无需重新获取")
            return cached_area

        logger.info(f"[mootdx] 需获取 {len(need_fetch)} 只股票的地区信息...")

        # 分流：沪深 vs 北交所
        hs_symbols = [s for s in need_fetch if self._is_hs_symbol(s)]
        bse_symbols = [s for s in need_fetch if self._is_bse_symbol(s)]

        new_area = {}

        # 沪深股票：mootdx F10
        if hs_symbols:
            logger.info(f"[mootdx] 沪深股票 {len(hs_symbols)} 只，使用 F10 查询...")
            f10_data = self._batch_fetch_f10(hs_symbols)
            for symbol, data in f10_data.items():
                area = self._parse_area(data)
                if area:
                    new_area[symbol] = area

        # 北交所股票：AkShare BSE API
        if bse_symbols:
            logger.info(f"[mootdx] 北交所股票 {len(bse_symbols)} 只，使用 BSE API 查询...")
            _, bse_area = self._fetch_bse_mapping()
            for symbol in bse_symbols:
                if symbol in bse_area:
                    new_area[symbol] = bse_area[symbol]

        # 合并缓存
        self._cache_data["area"] = {**cached_area, **new_area}
        self._save_cache()

        coverage = len(self._cache_data["area"]) / len(all_symbols) * 100 if all_symbols else 0
        logger.info(f"[mootdx] 地区覆盖率: {coverage:.1f}% ({len(self._cache_data['area'])}/{len(all_symbols)})")

        return self._cache_data["area"]

    def health_check(self) -> bool:
        """快速健康检查（测试 TCP 连接）"""
        try:
            quotes = self._quotes
            if quotes is None:
                return False
            # 测试获取一只股票的 F10
            data = quotes.F10("000001")
            return data is not None and len(data) > 0
        except Exception as e:
            logger.warning(f"[mootdx] 健康检查失败: {e}")
            return False