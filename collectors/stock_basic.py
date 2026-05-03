"""
股票基础信息采集器（重构版）

使用 DataOrchestrator 进行数据采集，自动补齐行业/地域字段
"""
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List

from sqlalchemy.dialects.mysql import insert

from collectors.base import BaseCollector
from services.data_orchestrator import orchestrator
from services.field_merger import FieldMerger
from models import StockBasic
from config import config
from utils import logger, TaskStoppedException


class StockBasicCollector(BaseCollector):
    """股票基础信息采集器

    使用编排器自动调度数据源，补齐行业/地域字段
    """

    def __init__(self, engine=None):
        super().__init__(engine)
        self.orchestrator = orchestrator

    def collect(
        self,
        progress_callback: Callable[[int, int, str], None] = None,
        stop_check: Callable[[], bool] = None
    ) -> Dict[str, Any]:
        """
        执行股票基础信息采集

        Args:
            progress_callback: 进度回调 (current, total, stage)
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        log_entry = self._create_log_entry("股票基础信息采集", "basic")

        try:
            # Step 1: 使用编排器采集数据（含行业/地域补齐）
            df = self.orchestrator.collect_stock_basic(progress_callback)

            if stop_check and stop_check():
                raise TaskStoppedException()

            if df is None or df.empty:
                raise Exception("采集数据为空")

            # Step 2: 数据转换
            df = self._transform_data(df)

            # Step 3: 保存到数据库
            saved_count = self._save_to_db(df, progress_callback)

            # 完成日志
            log_entry = self._finalize_log_entry(
                log_entry,
                success_count=saved_count,
                failed_count=len(df) - saved_count,
                status="success"
            )

            # 保存日志
            self._save_collect_log(**log_entry, extra_info=self.orchestrator.get_field_report())

            return {
                "success": True,
                "total": len(df),
                "saved": saved_count,
                "field_report": self.orchestrator.get_field_report()
            }

        except TaskStoppedException:
            log_entry = self._finalize_log_entry(
                log_entry,
                success_count=0,
                failed_count=0,
                status="stopped",
                error_msg="用户停止任务"
            )
            self._save_collect_log(**log_entry)
            return {"success": False, "status": "stopped"}

        except Exception as e:
            logger.error(f"股票基础信息采集失败: {e}")
            log_entry = self._finalize_log_entry(
                log_entry,
                success_count=0,
                failed_count=0,
                status="failed",
                error_msg=str(e)
            )
            self._save_collect_log(**log_entry)
            return {"success": False, "error": str(e)}

    def _clean_encoding(self, text: str) -> str:
        """清理文本中的编码乱码"""
        if text is None or pd.isna(text):
            return ""
        text = str(text)
        # 移除 UTF-8 替换字符和非法代理对字符
        import re
        # 移除替换字符
        text = re.sub(r'�', '', text)
        # 移除非法代理对字符
        text = re.sub(r'[\ud800-\udfff]', '', text)
        # 移除控制字符（保留换行和制表符）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text.strip()

    def _transform_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换数据格式为标准格式"""
        if df is None or df.empty:
            return df

        # 标准化列名
        df = FieldMerger.normalize_columns(df)

        # 清理编码问题列
        for col in ['industry', 'area', 'name']:
            if col in df.columns:
                df[col] = df[col].apply(self._clean_encoding)

        # 确保 symbol 列存在
        if 'symbol' not in df.columns:
            # 尝试从其他列获取
            for col in ['代码', 'code', 'dm']:
                if col in df.columns:
                    df['symbol'] = df[col]
                    break

        # 清理 symbol 格式：去除 bj/sh/sz 前缀，确保是6位数字
        df['symbol'] = df['symbol'].astype(str).str.replace(r'^(bj|sh|sz)', '', regex=True).str.zfill(6)

        # 构建 ts_code
        df['ts_code'] = df['symbol'].apply(self._build_ts_code)

        # 重命名列
        rename_map = {
            'symbol': 'symbol',
            'name': 'name',
            'industry': 'industry',
            'area': 'area',
            'ts_code': 'ts_code'
        }

        for old_name, new_name in rename_map.items():
            if old_name in df.columns and new_name not in df.columns:
                df[new_name] = df[old_name]

        # 填充默认值
        if 'list_status' not in df.columns:
            df['list_status'] = 'L'

        if 'market' not in df.columns:
            df['market'] = df['ts_code'].apply(lambda x: x.split('.')[-1] if '.' in x else 'SZ')

        return df

    def _build_ts_code(self, symbol: str) -> str:
        """构建 ts_code 格式"""
        if symbol is None:
            return None

        symbol = str(symbol).strip()

        # 已有后缀
        if '.' in symbol:
            return symbol

        # 根据代码判断市场
        if symbol.startswith('6'):
            return f"{symbol}.SH"
        elif symbol.startswith(('0', '3')):
            return f"{symbol}.SZ"
        elif symbol.startswith(('4', '8', '92', '93')):
            return f"{symbol}.BJ"
        else:
            return f"{symbol}.SZ"

    def _save_to_db(
        self,
        df: pd.DataFrame,
        progress_callback: Callable[[int, int, str], None] = None
    ) -> int:
        """保存数据到数据库"""
        if df is None or df.empty:
            return 0

        session = self.Session()
        saved_count = 0

        try:
            # 批量插入/更新
            records = df.to_dict('records')
            batch_size = config.collector.batch_size

            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]

                for record in batch:
                    # 使用 UPSERT
                    stmt = insert(StockBasic).values(
                        ts_code=record.get('ts_code'),
                        symbol=record.get('symbol'),
                        name=record.get('name'),
                        industry=record.get('industry', '未知'),
                        area=record.get('area', ''),
                        market=record.get('market', 'SZ'),
                        list_status=record.get('list_status', 'L')
                    ).on_duplicate_key_update(
                        name=record.get('name'),
                        industry=record.get('industry', '未知'),
                        area=record.get('area', '')
                    )
                    session.execute(stmt)

                session.commit()
                saved_count += len(batch)

                if progress_callback:
                    progress_callback(saved_count, len(records), "保存数据")

            logger.info(f"保存 {saved_count} 条股票基础信息到数据库")

        except Exception as e:
            session.rollback()
            logger.error(f"保存数据失败: {e}")
            raise
        finally:
            session.close()

        return saved_count

    def get_stock_list(self) -> List[str]:
        """获取已采集的股票代码列表"""
        session = self.Session()
        try:
            stocks = session.query(StockBasic.ts_code).filter(
                StockBasic.list_status == 'L'
            ).all()
            return [s[0] for s in stocks]
        finally:
            session.close()