"""
Tushare Pro 数据源适配器

Tushare Pro 是国内知名的金融数据接口，支持A股全市场（含北交所）。
需要注册获取 token: https://tushare.pro

特点：
- 覆盖 A 股全市场含北交所
- 支持日/周/月/分钟 K 线
- 支持前复权/后复权
- 免费注册送积分，付费 200-500/年
"""
from __future__ import annotations

import tushare as ts
from typing import Dict, List, Optional

import pandas as pd

from modules.collector.adapters.base import DataProvider, DataCategory, ProviderCapability
from utils import logger


class TushareProvider(DataProvider):
    """Tushare Pro 数据源适配器

    支持A股全市场（含北交所920xxx）的K线数据获取。
    """

    _token: Optional[str] = None
    _api: Optional[object] = None

    def __init__(self, token: Optional[str] = None):
        """初始化 Tushare Provider

        Args:
            token: Tushare Pro API token，如未提供则尝试从环境变量 TUSHARE_TOKEN 读取
        """
        if token:
            self._token = token
        else:
            import os
            self._token = os.environ.get('TUSHARE_TOKEN')

        if self._token:
            try:
                ts.set_token(self._token)
                self._api = ts.pro_api()
                logger.info("[tushare] 初始化成功")
            except Exception as e:
                logger.error(f"[tushare] 初始化失败: {e}")
        else:
            logger.warning("[tushare] 未配置 token，请设置 TUSHARE_TOKEN 环境变量")

    @property
    def provider_name(self) -> str:
        return "tushare"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["trade_date", "open", "high", "low", "close",
                        "pre_close", "volume", "amount"],
                quality_score=0.95,
                cost_type="paid",
                latency_ms=500,
            ),
        ]

    @property
    def field_mapping(self) -> Dict[DataCategory, Dict[str, str]]:
        return {
            DataCategory.KLINE_DAILY: {
                "ts_code": "symbol",
                "vol": "volume",
                "amount": "amount",
            },
        }

    def _normalize_code(self, symbol: str) -> str:
        """标准化股票代码为 tushare 格式

        tushare 格式: 000001.SZ 或 600000.SH 或 871981.BJ
        """
        code = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '').zfill(6)
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith(('0', '3')):
            return f"{code}.SZ"
        elif code.startswith(('4', '8', '92')):
            return f"{code}.BJ"
        else:
            return f"{code}.SZ"

    def fetch_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq"
    ) -> pd.DataFrame:
        """获取单只股票的日 K 线数据

        Args:
            symbol: 股票代码（6位数字或 ts_code 格式）
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）
            adjust: 复权类型（qfq=前复权, hfq=后复权, None=不复权）

        Returns:
            K 线数据 DataFrame
        """
        if not self._api:
            logger.warning("[tushare] API 未初始化，请检查 token")
            return pd.DataFrame()

        ts_code = self._normalize_code(symbol)

        # 标准化日期格式为 YYYYMMDD
        start_date = start_date.replace('-', '')
        end_date = end_date.replace('-', '')

        # 复权参数映射
        adj_map = {
            "qfq": "qfq",
            "hfq": "hfq",
            None: None,
        }
        adj = adj_map.get(adjust)

        try:
            # 调用 tushare daily 接口
            df = self._api.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is None or df.empty:
                logger.warning(f"[tushare] {symbol} K线数据为空")
                return pd.DataFrame()

            # 如果需要复权，获取复权因子并应用
            if adj and len(df) > 0:
                try:
                    adj_df = self._api.adj_factor(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date
                    )
                    if adj_df is not None and not adj_df.empty:
                        # 合并复权因子
                        df = df.merge(adj_df[['trade_date', 'adj_factor']], on='trade_date', how='left')
                        if adj == "qfq":
                            # 前复权：价格 * 复权因子
                            for col in ['open', 'high', 'low', 'close', 'pre_close']:
                                if col in df.columns:
                                    df[col] = df[col] * df['adj_factor']
                        elif adj == "hfq":
                            # 后复权：价格 / 复权因子
                            for col in ['open', 'high', 'low', 'close', 'pre_close']:
                                if col in df.columns:
                                    df[col] = df[col] / df['adj_factor']
                        df = df.drop(columns=['adj_factor'])
                except Exception as e:
                    logger.warning(f"[tushare] {symbol} 获取复权因子失败: {e}")

            # 应用字段映射
            df = self._normalize_dataframe(df, DataCategory.KLINE_DAILY)

            # 数值类型转换
            for col in ['open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # 确保日期格式
            if 'trade_date' in df.columns:
                df['trade_date'] = df['trade_date'].astype(str).str.replace('-', '')

            df = df.dropna(subset=['trade_date', 'close'])

            logger.info(f"[tushare] 获取 {symbol} K线 {len(df)} 条 ({start_date}~{end_date})")
            return df

        except Exception as e:
            logger.warning(f"[tushare] 获取 {symbol} K线失败: {e}")
            return pd.DataFrame()

    def health_check(self) -> bool:
        """健康检查"""
        if not self._api:
            return False
        try:
            # 测试获取最近一个交易日的数据
            from datetime import datetime, timedelta
            end = datetime.now().strftime('%Y%m%d')
            start = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
            df = self._api.daily(ts_code='000001.SZ', start_date=start, end_date=end)
            return df is not None and not df.empty
        except Exception:
            return False
