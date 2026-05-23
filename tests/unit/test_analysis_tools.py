import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from tools.analysis_base_tool import AnalysisToolBase
from tools.correlation_tool import CorrelationTool
from tools.descriptive_stats_tool import DescriptiveStatsTool
from tools.regression_tool import RegressionTool

SAMPLE_TABLE = """\
| Year | County | Value |
| --- | --- | --- |
| 2020 | A | 1.0 |
| 2021 | A | 2.0 |
| 2022 | A | 3.0 |
| 2023 | A | 4.0 |
"""


def test_parse_markdown_table():
    df = AnalysisToolBase.parse_markdown_table(None, SAMPLE_TABLE)
    assert list(df.columns) == ["Year", "County", "Value"]
    assert len(df) == 4
    assert float(df["Value"].iloc[-1]) == 4.0


def test_correlation_perfect_positive():
    tool = CorrelationTool()
    out = tool._run(
        table_data=SAMPLE_TABLE,
        col_a="Year",
        col_b="Value",
    )
    assert "Pearson Correlation:" in out
    assert "1.0000" in out or "1.0" in out


def test_descriptive_stats_numeric_columns():
    tool = DescriptiveStatsTool()
    out = tool._run(table_data=SAMPLE_TABLE)
    assert "Summary Statistics:" in out
    assert "Value" in out
    assert "mean" in out.lower()


def test_regression_ols_includes_target():
    tool = RegressionTool()
    out = tool._run(table_data=SAMPLE_TABLE, target_col="Value")
    assert "OLS Regression Results" in out or "R-squared" in out


WIDE_TABLE = """\
| place_key | Year | datacommons:Percent_Person_WithDiabetes | datacommons:Count_Person_BelowPovertyLevelInThePast12Months |
| --- | --- | --- | --- |
| geoId/18001 | 2021 | 10.5 | 1200 |
| geoId/18003 | 2021 | 11.2 | 1500 |
| geoId/18005 | 2021 | 9.8 | 900 |
"""


def test_correlation_on_wide_indicator_columns():
    tool = CorrelationTool()
    out = tool._run(
        table_data=WIDE_TABLE,
        col_a="datacommons:Percent_Person_WithDiabetes",
        col_b="datacommons:Count_Person_BelowPovertyLevelInThePast12Months",
    )
    assert "Pearson Correlation:" in out
    assert "Error" not in out.split(":")[0]
