import pandas as pd
from io import StringIO
from langchain.tools import StructuredTool

class AnalysisToolBase(StructuredTool):
    """Base class providing Markdown table parsing for Data Commons observations."""
    
    def parse_markdown_table(self, table_str: str) -> pd.DataFrame:
        """
        Converts the Markdown table output from get_observations into a DataFrame.
        This handles the '| Column |' format specified in the system prompt.
        """
        # Clean up lines: remove leading/trailing whitespace and pipes
        lines = [line.strip().strip('|') for line in table_str.strip().split('\n')]
        
        if len(lines) < 3:
            raise ValueError("Observation data is too short or not in table format.")
        
        # Header is line 0, data starts from line 2 (skipping the |---| separator)
        header = lines[0]
        data_rows = [l for l in lines[2:] if l.strip()]
        
        # Reconstruct as CSV string for efficient loading
        processed_lines = [header] + data_rows
        csv_content = "\n".join([",".join([cell.strip() for cell in l.split('|')]) for l in processed_lines])
        
        return pd.read_csv(StringIO(csv_content))