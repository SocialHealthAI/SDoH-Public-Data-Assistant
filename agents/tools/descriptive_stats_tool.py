import pandas as pd
import numpy as np
from pydantic import BaseModel, Field
from tools.analysis_base_tool import AnalysisToolBase

class DescriptiveStatsInput(BaseModel):
    table_data: str = Field(description="The full Markdown table string received from get_observations.")

class DescriptiveStatsTool(AnalysisToolBase):
    def __init__(self):
        super().__init__(
            name="descriptive_stats",
            description="Generates summary statistics (mean, median, std, etc.) for numeric columns in a table.",
            args_schema=DescriptiveStatsInput,
            func=self._run
        )

    def _run(self, table_data: str) -> str:
        try:
            df = self.parse_markdown_table(table_data)
            # Convert applicable columns to numeric and isolate them
            df = df.apply(pd.to_numeric, errors='ignore')
            numeric_df = df.select_dtypes(include=[np.number])
            
            if numeric_df.empty:
                return "Error: No numeric data found in the table to summarize."
            
            summary = numeric_df.describe().to_string()
            return f"Summary Statistics:\n{summary}"
        except Exception as e:
            return f"Descriptive Stats Error: {str(e)}"