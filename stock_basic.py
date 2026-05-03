"""
股票基础信息采集模块
支持多数据源自动降级
"""
import pandas as pd
from typing import List, Optional, Callable
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.mysql import insert

from config import config
from models import Base, StockBasic, CollectLog
from utils import logger, retry, RateLimiter, TaskStoppedException
from data_source import data_source_adapter


class StockBasicCollector:
    """股票基础信息采集器"""

    def __init__(self, engine=None):
        """
        初始化采集器

        Args:
            engine: SQLAlchemy 引擎，如果为 None 则自动创建
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
        logger.info("数据表创建/检查完成")

    @retry(max_retries=5, exceptions=(Exception,))
    def fetch_stock_info(self) -> pd.DataFrame:
        """
        获取 A股所有股票基础信息（使用数据源适配器）

        Returns:
            包含股票基础信息的 DataFrame
        """
        logger.info("开始获取股票基础信息...")

        self.rate_limiter.wait()

        # 使用数据源适配器获取数据（支持自动降级）
        source = data_source_adapter.get_current_source()
        df = data_source_adapter.fetch_stock_basic(source)

        logger.info(f"获取到 {len(df)} 条股票基础信息")
        return df

    @retry(max_retries=5, exceptions=(Exception,))
    def fetch_stock_info_extended(self) -> pd.DataFrame:
        """
        获取更详细的股票信息（包含行业、上市日期等）

        Returns:
            包含详细股票信息的 DataFrame
        """
        logger.info("开始获取详细股票信息...")

        self.rate_limiter.wait()

        try:
            # 使用数据源适配器获取实时行情数据（包含基本信息）
            df = data_source_adapter.fetch_realtime_with_fallback()

            # 获取行业板块映射（股票代码 -> 行业名称）
            industry_map = self._fetch_industry_mapping()
            if industry_map:
                df['所属行业'] = df['代码'].map(industry_map).fillna('未知')
                logger.info(f"成功映射 {len(industry_map)} 个行业分类")
            else:
                df['所属行业'] = '未知'
                logger.warning("行业映射获取失败，行业字段使用默认值")

            # 获取地域映射（股票代码 -> 地域名称）
            area_map = self._fetch_area_mapping()
            if area_map:
                df['地域'] = df['代码'].map(area_map).fillna('')
                logger.info(f"成功映射 {len(area_map)} 个地域分类")
            else:
                df['地域'] = ''
                logger.warning("地域映射获取失败，地域字段使用空值")

            df['market'] = '主板'  # 默认设置，后续可根据代码判断

            # 根据股票代码判断市场类型
            def get_market(code):
                code_str = str(code)
                if code_str.startswith('6'):
                    if code_str.startswith('68'):
                        return '科创板'
                    return '主板-SH'
                elif code_str.startswith('0'):
                    return '主板-SZ'
                elif code_str.startswith('3'):
                    return '创业板'
                elif code_str.startswith('8') or code_str.startswith('4'):
                    return '北交所'
                return '主板'

            df['market'] = df['代码'].apply(get_market)

            logger.info(f"获取到详细股票信息 {len(df)} 条")
            return df

        except Exception as e:
            logger.warning(f"获取详细股票信息失败: {e}，使用基础信息接口")
            return self.fetch_stock_info()

    def _fetch_industry_mapping(self) -> dict:
        """
        获取股票行业分类映射（股票代码 -> 行业名称）
        尝试多种数据源获取行业信息

        Returns:
            {股票代码: 行业名称} 字典
        """
        import akshare as ak

        industry_map = {}

        # 方法1：东方财富行业板块接口
        try:
            logger.info("尝试东方财富行业板块接口获取行业映射...")
            industry_boards = ak.stock_board_industry_name_em()
            if industry_boards is not None and not industry_boards.empty:
                board_names = industry_boards['板块名称'].tolist()
                logger.info(f"东方财富获取到 {len(board_names)} 个行业板块")

                for i, board_name in enumerate(board_names):
                    try:
                        self.rate_limiter.wait()
                        board_stocks = ak.stock_board_industry_cons_em(symbol=board_name)
                        if board_stocks is not None and not board_stocks.empty:
                            for _, row in board_stocks.iterrows():
                                code = str(row.get('代码', ''))
                                if code and code not in industry_map:
                                    industry_map[code] = board_name
                    except Exception as e:
                        logger.debug(f"获取行业板块 [{board_name}] 成分股失败: {e}")
                        continue

                    if (i + 1) % 20 == 0:
                        logger.info(f"行业板块处理进度: {i+1}/{len(board_names)}, 已映射 {len(industry_map)} 只股票")

                if industry_map:
                    logger.info(f"东方财富行业映射完成，共 {len(industry_map)} 只股票")
                    return industry_map
        except Exception as e:
            logger.warning(f"东方财富行业板块接口失败: {e}")

        # 方法2：新浪行业分类接口（备用）
        try:
            logger.info("尝试新浪接口获取行业映射...")
            # 新浪行业分类
            industry_df = ak.stock_industry_category_sina()
            if industry_df is not None and not industry_df.empty:
                for _, row in industry_df.iterrows():
                    code = str(row.get('代码', row.get('code', '')))
                    industry = row.get('行业', row.get('industry', ''))
                    if code and industry and code not in industry_map:
                        industry_map[code] = industry
                logger.info(f"新浪行业映射获取到 {len(industry_map)} 只股票")
        except Exception as e:
            logger.warning(f"新浪行业接口失败: {e}")

        # 方法3：腾讯行业分类接口（备用）
        if not industry_map:
            try:
                logger.info("尝试腾讯接口获取行业映射...")
                # 使用腾讯实时行情中的行业信息
                realtime_df = ak.stock_zh_a_spot_em()
                if realtime_df is not None and not realtime_df.empty:
                    # 检查是否有行业列
                    industry_col = None
                    for col in ['行业', '所属行业', 'industry']:
                        if col in realtime_df.columns:
                            industry_col = col
                            break

                    if industry_col:
                        for _, row in realtime_df.iterrows():
                            code = str(row.get('代码', ''))
                            industry = row.get(industry_col, '')
                            if code and industry and code not in industry_map:
                                industry_map[code] = industry
                        logger.info(f"从实时行情获取到 {len(industry_map)} 只股票的行业信息")
            except Exception as e:
                logger.warning(f"腾讯/实时行情行业接口失败: {e}")

        if industry_map:
            logger.info(f"行业映射完成，共 {len(industry_map)} 只股票获得行业分类")
        else:
            logger.warning("所有行业数据源都失败，行业字段将使用默认值")

        return industry_map

    def _fetch_area_mapping(self) -> dict:
        """
        获取股票地域映射（股票代码 -> 地域名称）
        尝试多种数据源获取地域信息

        Returns:
            {股票代码: 地域名称} 字典
        """
        import akshare as ak

        area_map = {}

        # 方法1：尝试从股票基本信息接口获取地域
        try:
            logger.info("尝试获取地域信息...")
            # 新浪地域分类
            area_df = ak.stock_area_category_sina()
            if area_df is not None and not area_df.empty:
                for _, row in area_df.iterrows():
                    code = str(row.get('代码', row.get('code', '')))
                    area = row.get('地域', row.get('地区', row.get('area', '')))
                    if code and area and code not in area_map:
                        area_map[code] = area
                logger.info(f"新浪地域映射获取到 {len(area_map)} 只股票")
        except Exception as e:
            logger.warning(f"新浪地域接口失败: {e}")

        # 方法2：如果上面失败，尝试从其他接口获取
        if not area_map:
            try:
                logger.info("尝试备用接口获取地域...")
                # 从股票列表接口尝试获取
                stock_info = ak.stock_info_a_code_name()
                if stock_info is not None:
                    # 这个接口通常只有代码和名称，地域需要其他方式
                    pass
            except Exception as e:
                logger.debug(f"备用地域接口失败: {e}")

        if area_map:
            logger.info(f"地域映射完成，共 {len(area_map)} 只股票获得地域信息")
        else:
            logger.warning("地域数据获取失败，地域字段将使用空值")

        return area_map

    def transform_data(self, df: pd.DataFrame) -> List[dict]:
        """
        转换数据格式以适配数据库模型

        Args:
            df: 原始数据 DataFrame

        Returns:
            转换后的数据列表
        """
        records = []

        for _, row in df.iterrows():
            # 构造 ts_code
            code = str(row.get('代码', row.get('code', '')))
            name = row.get('名称', row.get('name', ''))

            # 根据代码前缀判断市场
            if code.startswith('6'):
                ts_code = f"{code}.SH"
            else:
                ts_code = f"{code}.SZ"

            record = {
                'ts_code': ts_code,
                'symbol': code,
                'name': name,
                'area': row.get('地域', None),
                'industry': row.get('行业', row.get('所属行业', None)),
                'market': row.get('market', row.get('市场类型', None)),
                'list_date': self._parse_date(row.get('上市日期', None)),
                'list_status': 'L',
                'delist_date': None,
                'is_hs': None,
            }
            records.append(record)

        return records

    def _parse_date(self, date_val) -> Optional[datetime]:
        """解析日期（支持多种格式）"""
        if pd.isna(date_val) or date_val is None:
            return None
        try:
            if isinstance(date_val, str):
                # 尝试多种日期格式
                for fmt in ['%Y-%m-%d', '%Y%m%d']:
                    try:
                        return datetime.strptime(date_val, fmt).date()
                    except:
                        continue
            elif isinstance(date_val, datetime):
                return date_val.date()
            else:
                return None
        except:
            return None

    def save_to_db(self, records: List[dict], batch_size: int = 500):
        """
        批量保存数据到数据库（使用 UPSERT）

        Args:
            records: 数据记录列表
            batch_size: 批量插入大小
        """
        logger.info(f"开始保存 {len(records)} 条股票基础信息...")

        session = self.Session()
        try:
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]

                # 使用 INSERT ... ON DUPLICATE KEY UPDATE
                stmt = insert(StockBasic).values(batch)
                update_dict = {
                    'name': stmt.inserted.name,
                    'area': stmt.inserted.area,
                    'industry': stmt.inserted.industry,
                    'market': stmt.inserted.market,
                    'list_date': stmt.inserted.list_date,
                    'list_status': stmt.inserted.list_status,
                    'delist_date': stmt.inserted.delist_date,
                    'is_hs': stmt.inserted.is_hs,
                    'updated_at': datetime.now(),
                }
                stmt = stmt.on_duplicate_key_update(**update_dict)

                session.execute(stmt)
                session.commit()

                logger.info(f"已保存 {min(i + batch_size, len(records))}/{len(records)} 条")

        except Exception as e:
            session.rollback()
            logger.error(f"保存数据失败: {e}")
            raise
        finally:
            session.close()

        logger.info("股票基础信息保存完成")

    def collect(self, use_extended: bool = True, stop_check: Optional[Callable[[], bool]] = None) -> int:
        """
        执行采集流程

        Args:
            use_extended: 是否使用扩展接口获取详细信息
            stop_check: 停止检查回调函数，返回 True 表示应停止

        Returns:
            采集的记录数量
        """
        from datetime import datetime
        start_time = datetime.now()
        task_name = f"stock_basic_{start_time.strftime('%Y%m%d_%H%M%S')}"

        # 确保表存在
        self.create_table()

        # 检查停止信号
        if stop_check and stop_check():
            raise TaskStoppedException("用户请求停止任务")

        try:
            # 获取数据
            if use_extended:
                df = self.fetch_stock_info_extended()
            else:
                df = self.fetch_stock_info()

            # 转换数据前检查停止
            if stop_check and stop_check():
                raise TaskStoppedException("用户请求停止任务")

            # 转换数据
            records = self.transform_data(df)

            # 保存数据前检查停止
            if stop_check and stop_check():
                raise TaskStoppedException("用户请求停止任务")

            # 保存数据
            self.save_to_db(records)

            count = len(records)

            # 记录采集日志
            self._save_collect_log(task_name, 'basic', start_time, count, 0, 'success')

            return count

        except TaskStoppedException:
            # 记录停止日志
            self._save_collect_log(task_name, 'basic', start_time, 0, 0, 'stopped', '用户请求停止')
            raise

        except Exception as e:
            # 记录失败日志
            self._save_collect_log(task_name, 'basic', start_time, 0, 0, 'failed', str(e))
            raise

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


if __name__ == "__main__":
    # 单独运行测试
    collector = StockBasicCollector()
    count = collector.collect(use_extended=True)
    print(f"采集完成，共 {count} 条记录")
