"""测试字段合并器"""
import pandas as pd
import pytest
from modules.collector.services.field_merger import FieldMerger


class TestFieldMerger:
    """测试 FieldMerger"""

    def test_normalize_columns_chinese_to_english(self):
        """测试中文列名标准化为英文"""
        df = pd.DataFrame({
            "代码": ["000001", "000002"],
            "名称": ["平安银行", "万科A"],
        })
        result = FieldMerger.normalize_columns(df)
        assert "symbol" in result.columns
        assert "name" in result.columns
        assert "代码" not in result.columns

    def test_normalize_columns_mixed(self):
        """测试混合列名"""
        df = pd.DataFrame({
            "symbol": ["000001"],
            "名称": ["平安银行"],
            "开盘": [10.0],
        })
        result = FieldMerger.normalize_columns(df)
        assert "symbol" in result.columns
        assert "name" in result.columns
        assert "open" in result.columns

    def test_normalize_columns_empty(self):
        """测试空 DataFrame"""
        assert FieldMerger.normalize_columns(None) is None
        assert FieldMerger.normalize_columns(pd.DataFrame()).empty

    def test_get_symbol_column(self):
        """测试找出股票代码列"""
        df = pd.DataFrame({"symbol": ["000001"], "name": ["A"]})
        assert FieldMerger.get_symbol_column(df) == "symbol"

        df_cn = pd.DataFrame({"代码": ["000001"], "名称": ["A"]})
        assert FieldMerger.get_symbol_column(df_cn) == "代码"

    def test_get_symbol_column_no_match(self):
        """测试没有股票代码列"""
        df = pd.DataFrame({"name": ["A"]})
        assert FieldMerger.get_symbol_column(df) is None

    def test_merge_by_symbol_basic(self):
        """测试基本合并"""
        main = pd.DataFrame({
            "symbol": ["000001", "000002", "000003"],
            "name": ["A", "B", "C"]
        })
        supplement = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "industry": ["金融", "地产"]
        })
        result = FieldMerger.merge_by_symbol(main, supplement, fields=["industry"])
        assert "industry" in result.columns
        assert result.loc[result["symbol"] == "000001", "industry"].values[0] == "金融"
        assert result.loc[result["symbol"] == "000003", "industry"].isna().values[0]

    def test_merge_by_symbol_no_overwrite(self):
        """测试不覆盖已有值"""
        main = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "name": ["A", "B"],
            "industry": ["已有行业", None]
        })
        supplement = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "industry": ["新行业", "新行业2"]
        })
        result = FieldMerger.merge_by_symbol(main, supplement, fields=["industry"])
        # 已有值不被覆盖
        assert result.loc[result["symbol"] == "000001", "industry"].values[0] == "已有行业"
        # 空值被填充
        assert result.loc[result["symbol"] == "000002", "industry"].values[0] == "新行业2"

    def test_merge_by_symbol_overwrite(self):
        """测试覆盖已有值"""
        main = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "industry": ["旧行业", "旧行业2"]
        })
        supplement = pd.DataFrame({
            "symbol": ["000001"],
            "industry": ["新行业"]
        })
        result = FieldMerger.merge_by_symbol(main, supplement, fields=["industry"], overwrite=True)
        assert result.loc[result["symbol"] == "000001", "industry"].values[0] == "新行业"

    def test_merge_by_symbol_ts_code_format(self):
        """测试 ts_code 格式的合并"""
        main = pd.DataFrame({
            "symbol": ["000001.SZ", "000002.SZ"],
            "name": ["A", "B"]
        })
        supplement = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "industry": ["金融", "地产"]
        })
        result = FieldMerger.merge_by_symbol(main, supplement, fields=["industry"])
        assert result.loc[result["symbol"] == "000001.SZ", "industry"].values[0] == "金融"

    def test_merge_by_symbol_empty_main(self):
        """测试主 DataFrame 为空"""
        supp = pd.DataFrame({"symbol": ["000001"], "industry": ["金融"]})
        result = FieldMerger.merge_by_symbol(None, supp)
        assert not result.empty

    def test_merge_by_symbol_empty_supplement(self):
        """测试补充 DataFrame 为空"""
        main = pd.DataFrame({"symbol": ["000001"], "name": ["A"]})
        result = FieldMerger.merge_by_symbol(main, None)
        assert len(result) == 1

    def test_apply_mapping(self):
        """测试应用映射"""
        df = pd.DataFrame({
            "symbol": ["000001", "000002", "000003"],
            "name": ["A", "B", "C"]
        })
        mapping = {"000001": "金融", "000002": "地产"}
        result = FieldMerger.apply_mapping(df, mapping, "industry")
        assert "industry" in result.columns
        assert result.loc[result["symbol"] == "000001", "industry"].values[0] == "金融"
        assert result.loc[result["symbol"] == "000003", "industry"].isna().values[0]

    def test_apply_mapping_empty_df(self):
        """测试空 DataFrame 应用映射"""
        result = FieldMerger.apply_mapping(None, {"000001": "金融"}, "industry")
        assert result is None

    def test_apply_mapping_empty_mapping(self):
        """测试空映射"""
        df = pd.DataFrame({"symbol": ["000001"]})
        result = FieldMerger.apply_mapping(df, {}, "industry")
        assert "industry" not in result.columns or result["industry"].isna().all()

    def test_apply_mapping_only_fill_null(self):
        """测试只填充空值，不覆盖已有值"""
        df = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "industry": ["已有", None]
        })
        mapping = {"000001": "新值", "000002": "新值2"}
        result = FieldMerger.apply_mapping(df, mapping, "industry")
        assert result.loc[result["symbol"] == "000001", "industry"].values[0] == "已有"
        assert result.loc[result["symbol"] == "000002", "industry"].values[0] == "新值2"

    def test_apply_mapping_ts_code_format(self):
        """测试 ts_code 格式应用映射"""
        df = pd.DataFrame({
            "symbol": ["000001.SZ", "000002.SZ"],
        })
        mapping = {"000001": "金融"}
        result = FieldMerger.apply_mapping(df, mapping, "industry")
        assert result.loc[result["symbol"] == "000001.SZ", "industry"].values[0] == "金融"

    def test_aliases_completeness(self):
        """测试别名映射完整性"""
        assert "代码" in FieldMerger.FIELD_ALIASES["symbol"]
        assert "名称" in FieldMerger.FIELD_ALIASES["name"]
        assert "开盘" in FieldMerger.FIELD_ALIASES["open"]
        assert "最高" in FieldMerger.FIELD_ALIASES["high"]
        assert "最低" in FieldMerger.FIELD_ALIASES["low"]
        assert "收盘" in FieldMerger.FIELD_ALIASES["close"]
        assert "成交量" in FieldMerger.FIELD_ALIASES["volume"]
        assert "成交额" in FieldMerger.FIELD_ALIASES["amount"]
        assert "涨跌幅" in FieldMerger.FIELD_ALIASES["pct_chg"]
        assert "行业" in FieldMerger.FIELD_ALIASES["industry"]
        assert "地区" in FieldMerger.FIELD_ALIASES["area"]
