"""测试数据验证器"""
import pandas as pd
import pytest
from services.data_validator import DataValidator, FieldCoverage


class TestFieldCoverage:
    """测试 FieldCoverage 数据类"""

    def test_creation(self):
        fc = FieldCoverage("symbol", 100, 95, 0.95)
        assert fc.field_name == "symbol"
        assert fc.total_count == 100
        assert fc.covered_count == 95
        assert fc.coverage_rate == 0.95

    def test_to_dict(self):
        fc = FieldCoverage("industry", 100, 80, 0.8)
        d = fc.to_dict()
        assert d["field"] == "industry"
        assert d["total"] == 100
        assert d["covered"] == 80
        assert d["rate"] == 0.8


class TestDataValidator:
    """测试 DataValidator"""

    def setup_method(self):
        self.validator = DataValidator()

    def test_validate_empty_df(self):
        """测试空 DataFrame 验证"""
        assert not self.validator.validate(None, "stock_basic")
        assert not self.validator.validate(pd.DataFrame(), "stock_basic")

    def test_validate_stock_basic(self):
        """测试股票基础信息验证"""
        df = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "name": ["平安银行", "万科A"],
            "price": [10.0, 20.0]
        })
        assert self.validator.validate(df, "stock_basic")

    def test_validate_missing_required(self):
        """测试缺少必填字段"""
        df = pd.DataFrame({"price": [10.0, 20.0]})
        assert not self.validator.validate(df, "stock_basic")

    def test_check_fields_all_present(self):
        """测试检查所有字段都存在"""
        df = pd.DataFrame({"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5]})
        missing = self.validator.check_fields(df, ["open", "high", "low", "close"])
        assert missing == []

    def test_check_fields_missing(self):
        """测试检查到缺失字段"""
        df = pd.DataFrame({"open": [1.0], "close": [1.5]})
        missing = self.validator.check_fields(df, ["open", "high", "low", "close"])
        assert "high" in missing
        assert "low" in missing

    def test_check_fields_empty_df(self):
        """测试空 DataFrame 的字段检查"""
        missing = self.validator.check_fields(pd.DataFrame(), ["open", "close"])
        assert missing == ["open", "close"]

    def test_check_fields_all_nan(self):
        """测试所有值为空的字段"""
        df = pd.DataFrame({"open": [None, None], "close": [1.0, 2.0]})
        missing = self.validator.check_fields(df, ["open", "close"])
        assert "open" in missing

    def test_calculate_coverage(self):
        """测试覆盖率计算"""
        df = pd.DataFrame({
            "symbol": ["000001", "000002", "000003", None],
            "name": ["A", None, "C", "D"],
            "industry": ["金融", "地产", None, None],
            "area": [None, None, None, None]
        })
        report = self.validator.calculate_coverage(df, ["symbol", "name", "industry", "area"])

        coverage = {r.field_name: r for r in report}
        assert coverage["symbol"].coverage_rate == 0.75  # 3/4
        assert coverage["name"].coverage_rate == 0.75     # 3/4
        assert coverage["industry"].coverage_rate == 0.5   # 2/4
        assert coverage["area"].coverage_rate == 0.0       # 0/4

    def test_calculate_coverage_empty(self):
        """测试空 DataFrame 的覆盖率"""
        report = self.validator.calculate_coverage(pd.DataFrame(), ["symbol"])
        assert report == []

    def test_calculate_coverage_none_df(self):
        """测试 None DataFrame 的覆盖率"""
        report = self.validator.calculate_coverage(None, ["symbol"])
        assert report == []

    def test_find_missing_values(self):
        """测试找出缺失值"""
        df = pd.DataFrame({
            "symbol": ["000001", "000002", "000003"],
            "industry": ["金融", None, "地产"]
        })
        missing = self.validator.find_missing_values(df, "industry")
        assert len(missing) == 1
        assert missing.iloc[0]["symbol"] == "000002"

    def test_find_missing_values_no_such_field(self):
        """测试不存在的字段"""
        df = pd.DataFrame({"symbol": ["000001"]})
        missing = self.validator.find_missing_values(df, "nonexistent")
        assert missing.empty

    def test_get_quality_score_complete(self):
        """测试完整数据的质量评分"""
        df = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "name": ["A", "B"],
            "industry": ["金融", "地产"],
            "area": ["深圳", "北京"],
            "pct_chg": [1.0, 2.0],
            "turnover_rate": [0.5, 0.6]
        })
        score = self.validator.get_quality_score(df, "stock_basic")
        # 必填: symbol, name (2/2 = 1.0 * 0.7 = 0.7)
        # 建议: industry, area, pct_chg, turnover_rate (4/4 = 1.0 * 0.3 = 0.3)
        assert score == pytest.approx(1.0, rel=0.1)

    def test_get_quality_score_partial(self):
        """测试部分数据的质量评分"""
        df = pd.DataFrame({
            "symbol": ["000001"],
            "name": ["A"],
            # 缺少建议字段
        })
        score = self.validator.get_quality_score(df, "stock_basic")
        # 必填: symbol, name (2/2 = 1.0 * 0.7 = 0.7)
        # 建议: industry, area, pct_chg, turnover_rate (0/4 = 0.0 * 0.3 = 0.0)
        assert score == pytest.approx(0.7, rel=0.1)

    def test_get_quality_score_empty(self):
        """测试空数据的质量评分"""
        score = self.validator.get_quality_score(None, "stock_basic")
        assert score == 0.0

    def test_get_last_report(self):
        """测试获取最近一次报告"""
        df = pd.DataFrame({"symbol": ["000001", "000002"]})
        self.validator.calculate_coverage(df, ["symbol"])
        report = self.validator.get_last_report()
        assert len(report) == 1
        assert report[0].field_name == "symbol"

    def test_get_report_dict(self):
        """测试报告字典格式"""
        df = pd.DataFrame({"symbol": ["000001", "000002"]})
        self.validator.calculate_coverage(df, ["symbol"])
        d = self.validator.get_report_dict()
        assert "symbol" in d
        assert d["symbol"]["covered"] == 2

    def test_required_fields_defined(self):
        """测试必填字段定义完整"""
        assert "stock_basic" in DataValidator.REQUIRED_FIELDS
        assert "kline_daily" in DataValidator.REQUIRED_FIELDS
        assert "realtime_quote" in DataValidator.REQUIRED_FIELDS
        assert "symbol" in DataValidator.REQUIRED_FIELDS["stock_basic"]
        assert "name" in DataValidator.REQUIRED_FIELDS["stock_basic"]
