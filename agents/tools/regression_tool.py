import pandas as pd
import numpy as np
import statsmodels.api as sm
from typing import Type
from pydantic import BaseModel, Field
from tools.analysis_base_tool import AnalysisToolBase

class RegressionInput(BaseModel):
    table_data: str = Field(description="The full Markdown table string received from get_observations.")
    target_col: str = Field(description="The name of the dependent variable (y) column to predict.")

class RegressionTool(AnalysisToolBase):
    def __init__(self):
        super().__init__(
            name="regression_analysis",
            description="Performs OLS regression on numeric columns in a Markdown table.",
            args_schema=RegressionInput,
            func=self._run
        )

    def _run(self, table_data: str, target_col: str) -> str:
        try:
            df = self.parse_markdown_table(table_data)
            # Convert all possible columns to numeric for analysis
            df = df.apply(pd.to_numeric, errors='ignore')
            df = df.dropna().select_dtypes(include=[np.number])
            
            if target_col not in df.columns:
                return f"Error: '{target_col}' not found in the numeric columns: {list(df.columns)}"
            
            y = df[target_col]
            X = df.drop(columns=[target_col])
            X = sm.add_constant(X) # Adds the intercept term
            
            model = sm.OLS(y, X).fit()
            return model.summary().as_text()
        except Exception as e:
            return f"Regression Error: {str(e)}"