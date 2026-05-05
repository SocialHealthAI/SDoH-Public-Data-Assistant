import pandas as pd
from typing import List, Type
from pydantic import BaseModel, Field
from scipy.stats import pearsonr
from tools.analysis_base_tool import AnalysisToolBase

class CorrelationInput(BaseModel):
    table_data: str = Field(description="The full Markdown table string received from get_observations.")
    col_a: str = Field(description="The exact name of the first column to correlate.")
    col_b: str = Field(description="The exact name of the second column to correlate.")

class CorrelationTool(AnalysisToolBase):
    def __init__(self):
        super().__init__(
            name="calculate_correlation",
            description="Calculates Pearson correlation between two numeric columns in a Markdown table.",
            args_schema=CorrelationInput,
            func=self._run
        )

    def _run(self, table_data: str, col_a: str, col_b: str) -> str:
        try:
            df = self.parse_markdown_table(table_data)
            # Ensure columns are treated as numeric for math
            df[col_a] = pd.to_numeric(df[col_a], errors='coerce')
            df[col_b] = pd.to_numeric(df[col_b], errors='coerce')
            df = df.dropna(subset=[col_a, col_b])
            
            r_stat, p_val = pearsonr(df[col_a], df[col_b])
            return f"Pearson Correlation: {r_stat:.4f} (p-value: {p_val:.4f})"
        except Exception as e:
            return f"Correlation Error: {str(e)}"

