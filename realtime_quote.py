"""
股票实时行情接口模块
获取当天的盘口数据，支持多数据源自动降级
"""
import akshare as ak
import pandas as pd
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.mysql import insert

from config import config
from models import Base, StockRealtimeQuote, CollectLog
from utils import logger, retry, RateLimiter
from data_source import data_source_adapter


class RealtimeQuoteCollector:
    """实时行情采集器"""

    def __init__(self, engine=None):
        """
        初始化采集器

        Args:
            engine: SQLAlchemy 引擎
        """
        if engine is None:
            self.engine = create_engine(
                config.database.connection_url,
                pool_size=config.database.pool_size,
                max_overflow=config.database.max_overflow,
                pool_timeout=config.database.pool_timeout,
                pool_pre_ping=True
            )
        else:
            self.engine = engine

        self.Session = sessionmaker(bind=self.engine)
        self.rate_limiter = RateLimiter(config.collector.request_delay)

    def create_table(self):
        """创建数据表"""
        Base.metadata.create_all(self.engine)
        logger.info("实时行情数据表创建/检查完成")

    @retry(max_retries=3, exceptions=(Exception,))
    def fetch_realtime_quote_em(self) -> pd.DataFrame:
        """
        获取A股实时行情（使用数据源适配器，自动降级）

        Returns:
            实时行情 DataFrame
        """
        logger.info("开始获取A股实时行情...")

        self.rate_limiter.wait()

        # 使用数据源适配器获取数据（支持自动降级）
        df = data_source_adapter.fetch_realtime_with_fallback()
        logger.info(f"获取到 {len(df)} 条实时行情数据")
        return df

    @retry(max_retries=3, exceptions=(Exception,))
    def fetch_realtime_quote_sina(self, symbols: List[str] = None) -> pd.DataFrame:
        """
        获取A股实时行情（新浪数据源）- 备用数据源

        Args:
            symbols: 股票代码列表，如果为 None 则获取全部

        Returns:
            实时行情 DataFrame
        """
        logger.info("开始获取A股实时行情（新浪数据源）...")

        self.rate_limiter.wait()

        try:
            if symbols is None:
                # 使用数据源适配器获取新浪实时行情
                df = data_source_adapter.fetch_realtime_sina()
            else:
                # 获取指定股票的实时行情：先获取全量再筛选
                df_all = data_source_adapter.fetch_realtime_sina()
                # 新浪数据字段可能是 '代码' 或 'code'
                code_col = '代码' if '代码' in df_all.columns else 'code'
                df = df_all[df_all[code_col].isin(symbols)]

            logger.info(f"获取到 {len(df)} 条实时行情数据")
            return df

        except Exception as e:
            logger.error(f"获取实时行情（新浪）失败: {e}")
            raise

    @retry(max_retries=3, exceptions=(Exception,))
    def fetch_single_stock_quote(self, symbol: str) -> Optional[dict]:
        """
        获取单只股票的实时行情

        Args:
            symbol: 股票代码（不带交易所后缀）

        Returns:
            实时行情字典
        """
        self.rate_limiter.wait()

        try:
            # 使用东方财富个股实时行情
            df = ak.stock_individual_info_em(symbol=symbol)

            if df is None or df.empty:
                return None

            return df.to_dict('records')[0] if len(df) > 0 else None

        except Exception as e:
            logger.error(f"获取股票 {symbol} 实时行情失败: {e}")
            raise

    @retry(max_retries=3, exceptions=(Exception,))
    def fetch_bid_ask_data(self, symbol: str) -> Optional[dict]:
        """
        获取单只股票的买卖盘口数据

        Args:
            symbol: 股票代码

        Returns:
            盘口数据字典
        """
        self.rate_limiter.wait()

        try:
            # 获取实时行情（包含买卖盘）
            df = ak.stock_zh_a_spot_em()

            # 筛选指定股票
            row = df[df['代码'] == symbol]

            if row.empty:
                return None

            return row.to_dict('records')[0]

        except Exception as e:
            logger.error(f"获取股票 {symbol} 盘口数据失败: {e}")
            raise

    def transform_quote_data(self, df: pd.DataFrame) -> List[dict]:
        """
        转换实时行情数据格式

        Args:
            df: 原始数据 DataFrame

        Returns:
            转换后的数据列表
        """
        records = []

        for _, row in df.iterrows():
            record = {
                'symbol': str(row.get('代码', row.get('code', ''))),
                'name': row.get('名称', row.get('name', '')),
                'price': self._safe_decimal(row.get('最新价', row.get('price', None))),
                'open': self._safe_decimal(row.get('今开', row.get('open', None))),
                'high': self._safe_decimal(row.get('最高', row.get('high', None))),
                'low': self._safe_decimal(row.get('最低', row.get('low', None))),
                'pre_close': self._safe_decimal(row.get('昨收', row.get('pre_close', None))),
                'volume': self._safe_int(row.get('成交量', row.get('volume', None))),
                'amount': self._safe_decimal(row.get('成交额', row.get('amount', None))),
                'bid_price1': self._safe_decimal(row.get('买一', None)),
                'bid_volume1': self._safe_int(row.get('买��量', None)),
                'ask_price1': self._safe_decimal(row.get('卖一', None)),
                'ask_volume1': self._safe_int(row.get('卖一量', None)),
                'update_time': datetime.now(),
            }
            records.append(record)

        return records

    def _safe_decimal(self, val):
        """安全转换为数值"""
        if pd.isna(val) or val is None or val == '':
            return None
        try:
            return float(val)
        except:
            return None

    def _safe_int(self, val):
        """安全转换为整数"""
        if pd.isna(val) or val is None or val == '':
            return None
        try:
            return int(float(val))
        except:
            return None

    def save_to_db(self, records: List[dict]) -> int:
        """
        保存实时行情到数据库（UPSERT 模式）

        Args:
            records: 行情数据列表

        Returns:
            保存的记录数
        """
        if not records:
            return 0

        session = self.Session()
        try:
            # 使用 UPSERT 模式：存在则更新，不存在则插入
            stmt = insert(StockRealtimeQuote).values(records)
            stmt = stmt.on_duplicate_key_update(
                name=stmt.inserted.name,
                price=stmt.inserted.price,
                open=stmt.inserted.open,
                high=stmt.inserted.high,
                low=stmt.inserted.low,
                pre_close=stmt.inserted.pre_close,
                volume=stmt.inserted.volume,
                amount=stmt.inserted.amount,
                bid_price1=stmt.inserted.bid_price1,
                bid_volume1=stmt.inserted.bid_volume1,
                ask_price1=stmt.inserted.ask_price1,
                ask_volume1=stmt.inserted.ask_volume1,
                update_time=stmt.inserted.update_time,
            )
            session.execute(stmt)
            session.commit()

            logger.info(f"保存 {len(records)} 条实时行情数据")
            return len(records)

        except Exception as e:
            session.rollback()
            logger.error(f"保存实时行情数据失败: {e}")
            raise
        finally:
            session.close()

    def collect(self, source: str = 'em') -> dict:
        """
        采集实时行情

        Args:
            source: 数据源 'em'-东方财富 'sina'-新浪

        Returns:
            采集结果
        """
        from datetime import datetime
        start_time = datetime.now()
        task_name = f"realtime_{source}_{start_time.strftime('%Y%m%d_%H%M%S')}"

        # 确保表存在
        self.create_table()

        stats = {
            'total': 0,
            'success': False,
            'error': None
        }

        try:
            if source == 'em':
                df = self.fetch_realtime_quote_em()
            else:
                df = self.fetch_realtime_quote_sina()

            records = self.transform_quote_data(df)
            count = self.save_to_db(records)

            stats['total'] = count
            stats['success'] = True

            # 记录采集日志
            self._save_collect_log(task_name, 'realtime', start_time, count, 0, 'success')

        except Exception as e:
            stats['error'] = str(e)
            logger.error(f"实时行情采集失败: {e}")

            # 记录失败日志
            self._save_collect_log(task_name, 'realtime', start_time, 0, 0, 'failed', str(e))

        return stats

    def _save_collect_log(self, task_name: str, task_type: str,
                          start_time, success_count: int, failed_count: int,
                          status: str, error_msg: str = None):
        """保存采集日志到 collect_log 表"""
        from datetime import datetime
        try:
            session = self.Session()
            try:
                log = CollectLog(
                    task_name=task_name,
                    task_type=task_type,
                    start_time=start_time,
                    end_time=datetime.now(),
                    total_count=success_count + failed_count,
                    success_count=success_count,
                    failed_count=failed_count,
                    status=status,
                    error_msg=error_msg
                )
                session.add(log)
                session.commit()
                logger.info(f"采集日志已保存: {task_name} ({status})")
            except Exception as e:
                session.rollback()
                logger.warning(f"保存采集日志失败: {e}")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"保存采集日志失败(连接异常): {e}")

    def _get_all_realtime_df(self) -> pd.DataFrame:
        """
        获取全量实时行情数据（内部方法，避免重复拉取）

        Returns:
            实时行情 DataFrame
        """
        return data_source_adapter.fetch_realtime_with_fallback()

    def get_realtime_quote(self, symbol: str) -> Optional[dict]:
        """
        获取单只股票的实时行情（接口方法）

        Args:
            symbol: 股票代码

        Returns:
            实时行情字典
        """
        try:
            df = self._get_all_realtime_df()
            row = df[df['代码'] == symbol]

            if row.empty:
                return None

            data = row.to_dict('records')[0]
            return {
                'symbol': data.get('代码'),
                'name': data.get('名称'),
                'price': data.get('最新价'),
                'open': data.get('今开'),
                'high': data.get('最高'),
                'low': data.get('最低'),
                'pre_close': data.get('昨收'),
                'volume': data.get('成交量'),
                'amount': data.get('成交额'),
                'change': data.get('涨跌额'),
                'pct_chg': data.get('涨跌幅'),
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            logger.error(f"获取股票 {symbol} 实时行情失败: {e}")
            return None

    def get_top_gainers(self, limit: int = 10) -> List[dict]:
        """
        获取涨幅榜

        Args:
            limit: 返回数量

        Returns:
            涨幅榜列表
        """
        try:
            df = self._get_all_realtime_df()
            # 按涨跌幅排序
            df = df.sort_values(by='涨跌幅', ascending=False)
            top = df.head(limit)

            return top.to_dict('records')

        except Exception as e:
            logger.error(f"获取涨幅榜失败: {e}")
            return []

    def get_top_losers(self, limit: int = 10) -> List[dict]:
        """
        获取跌幅榜

        Args:
            limit: 返回数量

        Returns:
            跌幅榜列表
        """
        try:
            df = self._get_all_realtime_df()
            # 按涨跌幅排序
            df = df.sort_values(by='涨跌幅', ascending=True)
            top = df.head(limit)

            return top.to_dict('records')

        except Exception as e:
            logger.error(f"获取跌幅榜失败: {e}")
            return []

    def get_top_volume(self, limit: int = 10) -> List[dict]:
        """
        获取成交量榜

        Args:
            limit: 返回数量

        Returns:
            成交量榜列表
        """
        try:
            df = self._get_all_realtime_df()
            # 按成交量排序
            df = df.sort_values(by='成交量', ascending=False)
            top = df.head(limit)

            return top.to_dict('records')

        except Exception as e:
            logger.error(f"获取成交量榜失败: {e}")
            return []


if __name__ == "__main__":
    # 单独运行测试
    collector = RealtimeQuoteCollector()

    # 采集全部实时行情
    stats = collector.collect()
    print(f"采集结果: {stats}")

    # 获取单只股票行情
    quote = collector.get_realtime_quote('000001')
    print(f"平安银行行情: {quote}")

    # 获取涨幅榜
    gainers = collector.get_top_gainers(5)
    print(f"涨幅榜前5: {gainers}")