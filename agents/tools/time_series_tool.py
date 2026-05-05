import pandas as pd
import numpy as np
from pydantic import BaseModel, Field
from statsmodels.tsa.holtwinters import SimpleExpSmoothing
from tools.analysis_base_tool import AnalysisToolBase

class TimeSeriesInput(BaseModel):
    table_data: str = Field(description="The full Markdown table string received from get_observations.")
    target_col: str = Field(description="The numeric column to forecast.")
    steps: int = Field(default=3, description="Number of years to forecast into the future.")

class TimeSeriesTool(AnalysisToolBase):
    def __init__(self):
        super().__init__(
            name="time_series_forecast",
            description="Uses Simple Exponential Smoothing to forecast future values based on historical trends.",
            args_schema=TimeSeriesInput,
            func=self._run
        )

    def _run(self, table_data: str, target_col: str, steps: int = 3) -> str:
        try:
            df = self.parse_markdown_table(table_data)
            
            # Ensure the data is sorted by year for time-series integrity
            if 'Year' in df.columns:
                df['Year'] = pd.to_numeric(df['Year'])
                df = df.sort_values('Year')
            
            df[target_col] = pd.to_numeric(df[target_col], errors='coerce')
            data = df[target_col].dropna().values
            
            if len(data) < 3:
                return "Error: Insufficient data points for a reliable forecast (minimum 3 required)."

            # Fit Simple Exponential Smoothing model
            model = SimpleExpSmoothing(data, initialization_method="estimated").fit()
            forecast = model.forecast(steps)
            
            last_year = df['Year'].iloc[-1] if 'Year' in df.columns else 0
            result = f"Historical Average Level: {model.level[-1]:.2f}\n"
            result += f"Forecast for next {steps} years:\n"
            
            for i, val in enumerate(forecast, 1):
                result += f"Year {int(last_year + i)}: {val:.2f}\n"
                
            return result
        except Exception as e:
            return f"Time-Series Error: {str(e)}"