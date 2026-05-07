"""
Baostock 数据源适配器

Baostock 是证券宝提供的免费数据接口，无需注册。
支持 A 股日 K / 周 K / 月 K 数据。

网站: http://baostock.com
"""
from __future__ import annotations

import baostock as bs
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from modules.collector.adapters.base import DataProvider, DataCategory, ProviderCapability
from utils import logger


class BaostockProvider(DataProvider):
    """Baostock 数据源适配器

    提供日 K 线数据，免费无需注册。
    """

    _logged_in: bool = False

    def __init__(self):
        self._ensure_login()

    def _ensure_login(self):
        """确保 baostock 登录（登录后才能查询）"""
        if not self._logged_in:
            try:
                # 清除代理环境变量（防止企业代理阻塞 baostock HTTP 请求）
                import os
                for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
                    os.environ.pop(var, None)
                lg = bs.login()
                if lg.error_code == '0':
                    self._logged_in = True
                    logger.info("[baostock] 登录成功")
                else:
                    logger.error(f"[baostock] 登录失败: {lg.error_msg}")
            except Exception as e:
                logger.error(f"[baostock] 登录异常: {e}")

    @property
    def provider_name(self) -> str:
        return "baostock"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["trade_date", "open", "high", "low", "close",
                        "pre_close", "volume", "amount", "turnover_rate", "pct_chg"],
                quality_score=0.9,
                cost_type="free",
                latency_ms=800,
            ),
        ]

    @property
    def field_mapping(self) -> Dict[DataCategory, Dict[str, str]]:
        return {
            DataCategory.KLINE_DAILY: {
                "date": "trade_date",
                "preclose": "pre_close",
                "turn": "turnover_rate",
                "pctChg": "pct_chg",
            },
        }

    def _normalize_code(self, symbol: str) -> str:
        """标准化股票代码为 baostock 格式

        baostock 格式: sh.600000 或 sz.000001
        """
        code = symbol.replace('bj', '').replace('sh', '').replace('sz', '').zfill(6)
        if code.startswith('6'):
            return f"sh.{code}"
        elif code.startswith(('0', '3')):
            return f"sz.{code}"
        else:
            # 北交所及其他暂不支持
            return None

    def fetch_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq"
    ) -> pd.DataFrame:
        """获取单只股票的日 K 线数据

        Args:
            symbol: 股票代码（6 位数字或带前缀格式）
            start_date: 开始日期（YYYY-MM-DD 或 YYYYMMDD）
            end_date: 结束日期（YYYY-MM-DD 或 YYYYMMDD）
            adjust: 复权类型（qfq=前复权, hfq=后复权, None=不复权）

        Returns:
            K 线数据 DataFrame
        """
        self._ensure_login()

        # 标准化代码
        bs_code = self._normalize_code(symbol)
        if bs_code is None:
            logger.warning(f"[baostock] {symbol} 不支持的代码格式")
            return pd.DataFrame()

        # 标准化日期格式（转为 YYYY-MM-DD）
        if len(start_date) == 8:
            start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        if len(end_date) == 8:
            end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"

        # 复权参数映射
        adjust_map = {
            "qfq": "2",   # 前复权
            "hfq": "1",   # 后复权
            None: "3",    # 不复权
        }
        adjust_flag = adjust_map.get(adjust, "3")

        try:
            # 调用 baostock query_history_k_data_plus
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag=adjust_flag
            )

            if rs.error_code != '0':
                logger.warning(f"[baostock] {symbol} 查询失败: {rs.error_msg}")
                return pd.DataFrame()

            # 转换为 DataFrame
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                logger.warning(f"[baostock] {symbol} K 线数据为空")
                return pd.DataFrame()

            df = pd.DataFrame(data_list, columns=rs.fields)

            # 应用字段映射
            df = self._normalize_dataframe(df, DataCategory.KLINE_DAILY)

            # 确保日期格式统一（转为 YYYYMMDD）
            if 'trade_date' in df.columns:
                df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')

            # 数值类型转换
            for col in ['open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount', 'turnover_rate', 'pct_chg']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # 移除空数据行
            df = df.dropna(subset=['trade_date', 'close'])

            logger.info(f"[baostock] 获取 {symbol} K 线 {len(df)} 条 ({start_date}~{end_date})")
            return df

        except Exception as e:
            logger.warning(f"[baostock] 获取 {symbol} K 线失败: {e}")
            return pd.DataFrame()

    def health_check(self) -> bool:
        """健康检查"""
        self._ensure_login()
        if not self._logged_in:
            return False

        # 测试获取平安银行最近一天数据
        try:
            df = self.fetch_kline("000001", datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d"))
            return df is not None and not df.empty
        except Exception:
            return False