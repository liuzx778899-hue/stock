"""
JoinQuant 数据源适配器

JoinQuant（聚宽）提供的免费 K 线数据接口。
免费账号每日有限额，适合作为降级数据源。

特点：
- 全 A 股覆盖（不含北交所）
- 日 K 线数据
- 免费注册，每日额度限制
- 网站: https://www.joinquant.com
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from modules.collector.adapters.base import DataProvider, DataCategory, ProviderCapability
from utils import logger

try:
    import jqdatasdk as jq
except ImportError:
    jq = None
    logger.warning("[jqdata] jqdatasdk 未安装，请执行 pip install jqdatasdk")


def _get_credentials_from_db() -> tuple[Optional[str], Optional[str]]:
    """从 system_config 表读取凭证（优先级高于环境变量）"""
    try:
        from sqlalchemy import create_engine, text
        from common.crypto import decrypt_password
        import json
        from config import config

        engine = create_engine(config.database.connection_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT config_value FROM system_config WHERE config_key = 'datasource.jqdata.credentials'")
            ).fetchone()
            if row:
                data = json.loads(row[0])
                username = data.get('username')
                password = data.get('password')
                if password:
                    password = decrypt_password(password)
                return username, password
    except Exception as e:
        logger.debug(f"[jqdata] 从数据库读取凭证失败: {e}")
    return None, None


class JqdataProvider(DataProvider):
    """JoinQuant 数据源适配器

    提供日 K 线数据，免费（不含北交所）。
    """

    _username: Optional[str] = None
    _password: Optional[str] = None
    _logged_in: bool = False

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        """初始化 JoinQuant Provider

        Args:
            username: JoinQuant 账号（手机号）
            password: JoinQuant 密码
        """
        if jq is None:
            return

        if username and password:
            self._username = username
            self._password = password
        else:
            # 优先从数据库读取，其次环境变量
            self._username, self._password = _get_credentials_from_db()
            if not self._username or not self._password:
                import os
                self._username = self._username or os.environ.get('JQDATA_USERNAME')
                self._password = self._password or os.environ.get('JQDATA_PASSWORD')

        self._ensure_login()

    def _ensure_login(self):
        """确保 jqdata 登录"""
        if self._logged_in:
            return

        if not self._username or not self._password:
            logger.warning("[jqdata] 未配置账号密码，请在 Web 界面配置或设置 JQDATA_USERNAME 和 JQDATA_PASSWORD 环境变量")
            return

        try:
            jq.auth(self._username, self._password)
            self._logged_in = True
            remaining = jq.get_query_count()
            logger.info(f"[jqdata] 登录成功，剩余查询次数: {remaining}")
        except Exception as e:
            logger.error(f"[jqdata] 登录失败: {e}")

    @property
    def provider_name(self) -> str:
        return "jqdata"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["trade_date", "open", "high", "low", "close", "volume", "amount"],
                quality_score=0.85,
                cost_type="free",
                latency_ms=600,
            ),
        ]

    @property
    def field_mapping(self) -> Dict[DataCategory, Dict[str, str]]:
        return {
            DataCategory.KLINE_DAILY: {
                "date": "trade_date",
                "money": "amount",
            },
        }

    def _normalize_code(self, symbol: str) -> str:
        """标准化股票代码为 jqdata 格式

        jqdata 格式: 000001.XSHE 或 600000.XSHG
        """
        code = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '').zfill(6)
        if code.startswith('6'):
            return f"{code}.XSHG"
        elif code.startswith(('0', '3')):
            return f"{code}.XSHE"
        else:
            # 北交所及其他不支持
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
            symbol: 股票代码（6位数字）
            start_date: 开始日期（YYYY-MM-DD 或 YYYYMMDD）
            end_date: 结束日期（YYYY-MM-DD 或 YYYYMMDD）
            adjust: 复权类型（qfq=前复权, hfq=后复权, None=不复权）

        Returns:
            K 线数据 DataFrame
        """
        if jq is None:
            return pd.DataFrame()

        self._ensure_login()
        if not self._logged_in:
            return pd.DataFrame()

        jq_code = self._normalize_code(symbol)
        if jq_code is None:
            logger.warning(f"[jqdata] {symbol} 不支持的代码格式（北交所不支持）")
            return pd.DataFrame()

        # 标准化日期格式为 YYYY-MM-DD
        if len(start_date) == 8:
            start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        if len(end_date) == 8:
            end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"

        # 复权参数映射
        adj_map = {
            "qfq": "pre",
            "hfq": "post",
            None: "none",
        }
        fq = adj_map.get(adjust, "pre")

        try:
            # 调用 jqdata get_price
            df = jq.get_price(
                jq_code,
                start_date=start_date,
                end_date=end_date,
                frequency='daily',
                fields=['open', 'close', 'high', 'low', 'volume', 'money'],
                fq=fq
            )

            if df is None or df.empty:
                logger.warning(f"[jqdata] {symbol} K线数据为空")
                return pd.DataFrame()

            # jqdata 返回的索引是日期
            df = df.reset_index()
            df = df.rename(columns={'index': 'date'})

            # 应用字段映射
            df = self._normalize_dataframe(df, DataCategory.KLINE_DAILY)

            # 数值类型转换
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # 确保日期格式为 YYYYMMDD
            if 'trade_date' in df.columns:
                df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y%m%d')

            df = df.dropna(subset=['trade_date', 'close'])

            logger.info(f"[jqdata] 获取 {symbol} K线 {len(df)} 条 ({start_date}~{end_date})")
            return df

        except Exception as e:
            logger.warning(f"[jqdata] 获取 {symbol} K线失败: {e}")
            return pd.DataFrame()

    def health_check(self) -> bool:
        """健康检查"""
        if jq is None or not self._logged_in:
            return False
        try:
            remaining = jq.get_query_count()
            return remaining > 0
        except Exception:
            return False
