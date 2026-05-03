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

        # 匹配: ----行业名称--行业名称(N) 或 ----xxx--xxx(N)
        pattern = r'--+([^-]+)--\S*\(\d+\)'
        match = re.search(pattern, hyfx)
        if match:
            industry = match.group(1).strip()
            # 清理可能的乱码/后缀
            industry = re.sub(r'[ⅠⅡⅢⅡⅢ]+$', '', industry).strip()
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

    def _fetch_one_f10(self, symbol: str, use_thread_quotes: bool = False) -> Optional[dict]:
        """获取单只股票的 F10 数据"""
        quotes = self._get_thread_quotes() if use_thread_quotes else self._quotes
        if quotes is None:
            return None

        try:
            # mootdx F10 需要带市场前缀的代码（如 0000001）
            # 标准市场模式下直接用 6 位代码
            code = symbol.zfill(6)
            data = quotes.F10(code)
            return data
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

    # ---- DataProvider 接口实现 ----

    def fetch_industry_mapping(self) -> Dict[str, str]:
        """返回 {symbol: industry_name} 映射"""
        cache = self._load_cache()
        cached_industry = cache.get("industry", {})

        # 如果缓存有数据且未过期，直接返回
        if cached_industry and cache.get("updated_at"):
            return cached_industry

        # 获取股票列表（从 stock_basic 表或调用方传入）
        # 这里只获取缓存中不存在的股票
        from models import Session, StockBasic
        try:
            with Session() as session:
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

        # 批量 F10 查询
        f10_data = self._batch_fetch_f10(need_fetch)

        # 解析行业
        new_industry = {}
        for symbol, data in f10_data.items():
            industry = self._parse_industry(data)
            if industry:
                new_industry[symbol] = industry

        # 合并缓存
        self._cache_data["industry"] = {**cached_industry, **new_industry}
        self._save_cache()

        coverage = len(self._cache_data["industry"]) / len(all_symbols) * 100
        logger.info(f"[mootdx] 行业覆盖率: {coverage:.1f}% ({len(self._cache_data['industry'])}/{len(all_symbols)})")

        return self._cache_data["industry"]

    def fetch_area_mapping(self) -> Dict[str, str]:
        """返回 {symbol: area_name} 映射"""
        cache = self._load_cache()
        cached_area = cache.get("area", {})

        # 如果缓存有数据且未过期，直接返回
        if cached_area and cache.get("updated_at"):
            return cached_area

        # 获取股票列表
        from models import Session, StockBasic
        try:
            with Session() as session:
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

        # 批量 F10 查询（复用行业查询的缓存数据）
        f10_data = self._batch_fetch_f10(need_fetch)

        # 解析地区
        new_area = {}
        for symbol, data in f10_data.items():
            area = self._parse_area(data)
            if area:
                new_area[symbol] = area

        # 合并缓存
        self._cache_data["area"] = {**cached_area, **new_area}
        self._save_cache()

        coverage = len(self._cache_data["area"]) / len(all_symbols) * 100
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