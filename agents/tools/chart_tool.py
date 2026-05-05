# chart_tool.py (fully generalized)
from typing import Optional, Type, ClassVar, Any, Dict, List
from langchain.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage
from langchain.tools import Tool
import re
import json

class ChartToolInput(BaseModel):
    """Input for the ChartTool."""
    user_input: str = Field(..., description="The natural language description of the chart to generate")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional structured data in various formats: {'columns': [...], 'rows': [[...], ...]} or {key1: [values], key2: [values]}")
    csv: Optional[str] = Field(None, description="Optional CSV string with header")

def get_chart_langchain_tool(llm):
    chart_tool_instance = ChartTool(llm=llm)
    return Tool.from_function(
        func=chart_tool_instance._run,
        name=chart_tool_instance.name,
        description=chart_tool_instance.description,
        args_schema=chart_tool_instance.args_schema,
        return_direct=True,
    )

class ChartTool(BaseTool):
    name: ClassVar[str] = "generate_chart"
    description: ClassVar[str] = """Generate matplotlib chart code from natural language descriptions.
        ⚠️ CRITICAL REQUIREMENTS:
        1. This tool CANNOT fetch data - it only generates plotting code
        2. This tool CANNOT use pandas DataFrames
        3. You MUST pass actual data via 'csv' or 'data' parameter - DO NOT use user_input to describe data structure

        CORRECT WORKFLOW:
        Step 1: Fetch data using get_observations or other data tools
        Step 2: Extract the data values from tool outputs
        Step 3: Call generate_chart with:
        - user_input: Chart styling only (e.g., "scatter plot, gray markers, grid, title 'Obesity vs Poverty'")
        - csv: Actual data as CSV string (e.g., "Place,Obesity,Poverty\\nCounty1,30.2,12.3\\nCounty2,28.5,15.1\\n...")
            OR
        - data: Actual data as structured dict (e.g., {"Place": ["County1", "County2"], "Obesity": [30.2, 28.5], "Poverty": [12.3, 15.1]})

        WRONG - Never do this:
        generate_chart(user_input="assume df exists with columns X, Y, Z...")

        Returns: Self-contained Python/matplotlib code (not images)."""
    args_schema: ClassVar[Type[BaseModel]] = ChartToolInput

    llm: object = Field(..., description="The LLM to use for chart generation")
    _chart_prompt_template: PromptTemplate = PrivateAttr()
    _latest_result: dict = PrivateAttr(default=None)

    def __init__(self, llm: object, **kwargs):
        super().__init__(llm=llm, **kwargs)
        self._chart_prompt_template = PromptTemplate.from_template("""
            You generate Python code using only the matplotlib library to create a chart based on the user's request.
            You do not generate chart images, image markdown or data URIs.

            CRITICAL REQUIREMENTS:
            - Generate self-contained code with all data defined inline as Python lists/variables
            - NEVER assume external variables (like 'df') will be provided
            - If data is provided in the DATA section below, include it as inline variable definitions - do NOT create example/placeholder data
            - If any input data lists have missing values (None/null/NaN) or mismatched lengths, your code MUST:
              (1) build aligned rows (by shared index) and
              (2) filter out any rows missing required x/y values before plotting
              so that x and y arrays passed to plotting are the same length.
            - Do not use plt.show() or plt.savefig()
            - Do not save the plot to a file
            - Use only safe, standard plotting code
            - Do not import or access unsafe libraries (e.g., os, sys, subprocess)
            - Begin with a short explanation of what the chart shows
            - Follow the explanation with a valid Python code block enclosed in triple backticks
            - Examples of forbidden content: "![...](data:image/png;base64,...)", "data:image/png;base64,..." or any other embedded base64 image

            {data_instruction}

            User request: {user_input}
            """)

    def _coerce_missing(self, v: Any) -> Any:
        """Coerce common 'missing' sentinels into None."""
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"", "none", "null", "nan", "na", "n/a"}:
                return None
        return v

    def _align_by_index_min_len(self, data: Dict[str, List]) -> tuple[Dict[str, List], Optional[str]]:
        """
        Align ragged columns by shared index using the minimum length across columns.

        This avoids index-padding (which can introduce misalignment) while guaranteeing
        plotting code receives equal-length arrays. Any extra trailing values in longer
        columns are dropped.
        """
        if not data:
            return data, None

        lengths = [len(v) for v in data.values() if isinstance(v, list)]
        if not lengths:
            return data, None

        min_len = min(lengths)
        max_len = max(lengths)
        warning = None
        if min_len != max_len:
            warning = (
                f"Input columns had unequal lengths (min={min_len}, max={max_len}). "
                f"Aligned by shared index using the first {min_len} rows (truncated longer columns)."
            )

        aligned: Dict[str, List] = {}
        for k, v in data.items():
            if isinstance(v, list):
                aligned[k] = v[:min_len]
            else:
                aligned[str(k)] = v
        return aligned, warning

    def _normalize_data(self, data: Dict[str, Any]) -> tuple[Optional[Dict[str, List]], List[str]]:
        """
        Normalize various data formats into a consistent dict structure.
        Handles: {'columns': [...], 'rows': [[...]]}, direct {key: [values]}, etc.
        """
        if not data or not isinstance(data, dict):
            return None, []

        warnings: List[str] = []

        # Format 1: columns/rows structure
        if "columns" in data and "rows" in data:
            columns = data["columns"]
            rows = data["rows"]
            if not columns or not rows:
                return None

            # Create dict with column names as keys
            result = {str(col): [] for col in columns}
            for row in rows:
                for i, col in enumerate(columns):
                    # Pad missing cells with None to keep column lengths aligned
                    cell = row[i] if i < len(row) else None
                    result[str(col)].append(self._coerce_missing(cell))
            return result, warnings

        # Format 2: Direct key-value lists (already in good format)
        # Check if all values are lists
        if all(isinstance(v, list) for v in data.values()):
            cleaned = {
                str(k): [self._coerce_missing(x) for x in v]  # type: ignore[arg-type]
                for k, v in data.items()
            }
            aligned, warn = self._align_by_index_min_len(cleaned)
            if warn:
                warnings.append(warn)
            return aligned, warnings

        # Format 3: rows-only without columns (assume 2-column data)
        if "rows" in data and isinstance(data["rows"], list):
            try:
                rows = data["rows"]
                if rows and len(rows[0]) >= 2:
                    return {
                        "col_0": [self._coerce_missing(r[0]) for r in rows],
                        "col_1": [self._coerce_missing(r[1]) for r in rows],
                    }, warnings
            except Exception:
                pass

        return None, warnings

    def _parse_csv(self, csv_text: str) -> Optional[Dict[str, List]]:
        """Parse CSV text into dict format."""
        try:
            lines = [ln.strip() for ln in csv_text.strip().splitlines() if ln.strip()]
            if len(lines) < 2:
                return None

            # Parse header
            header = [h.strip() for h in re.split(r",\s*", lines[0])]
            result = {h: [] for h in header}

            # Parse data rows
            for line in lines[1:]:
                parts = [p.strip() for p in re.split(r",\s*", line)]
                for i, col in enumerate(header):
                    if i < len(parts):
                        val = parts[i]
                        # Try to parse as number, keep as string otherwise
                        try:
                            val = float(val) if '.' in val else int(val)
                        except ValueError:
                            pass
                        result[col].append(val)

            return result if result[header[0]] else None
        except Exception:
            return None

    def _format_data_for_prompt(self, parsed_data: Dict[str, List]) -> str:
        """Format parsed data as Python code snippet for the prompt."""
        lines = []
        for key, values in parsed_data.items():
            # Sanitize key to be valid Python identifier
            py_key = re.sub(r'[^a-zA-Z0-9_]', '_', key)
            if py_key[0].isdigit():
                py_key = 'col_' + py_key

            # Format the list
            if all((v is None) or isinstance(v, (int, float)) for v in values):
                lines.append(f"{py_key} = {values}")
            else:
                # Quote string values
                formatted_values = []
                for v in values:
                    if v is None:
                        formatted_values.append("None")
                    elif isinstance(v, str):
                        formatted_values.append(f"'{v}'")
                    else:
                        formatted_values.append(str(v))
                lines.append(f"{py_key} = [{', '.join(formatted_values)}]")

        return "\n".join(lines)

    def _run(self, user_input: str, data: Optional[dict] = None, csv: Optional[str] = None) -> str:
        """
        Generate matplotlib chart code based on user input and optional data.
        Returns a JSON-stringified dict containing explanation, code_block, and parsed data.
        """
        parsed_data = None
        warnings: List[str] = []

        # 1) Prefer structured `data`
        if data:
            parsed_data, warnings = self._normalize_data(data)

        # 2) Try csv argument
        if parsed_data is None and csv:
            parsed_data = self._parse_csv(csv)

        # 3) Try parsing user_input for CSV-like content
        if parsed_data is None:
            # Look for CSV-like patterns in the user input
            lines = user_input.strip().splitlines()
            if len(lines) >= 2:
                # Check if first line looks like CSV header
                first_line = lines[0].strip()
                if ',' in first_line:
                    maybe_csv = '\n'.join(lines)
                    parsed_data = self._parse_csv(maybe_csv)

        # Build the LLM prompt with strong data injection
        data_instruction = ""
        if parsed_data:
            data_code = self._format_data_for_prompt(parsed_data)
            data_instruction = f"""
**IMPORTANT: YOU MUST USE THIS EXACT DATA IN YOUR CODE:**

```python
# Use this data exactly as provided - DO NOT create example/placeholder data
{data_code}
```

DO NOT create placeholder, example, or fake data. Use ONLY the data provided above.
The variable names match the column/key names from the input data.
"""
        else:
            data_instruction = "No structured data provided. Generate appropriate example data if needed."

        query = self._chart_prompt_template.format(
            user_input=user_input,
            data_instruction=data_instruction
        )

        response_msg = self.llm.invoke([HumanMessage(content=query)])
        response = response_msg.content.strip()

        # Defensive strip: remove embedded images
        response = re.sub(r"!\[.*?\]\(\s*data:image/[a-zA-Z0-9]+;base64,[A-Za-z0-9+/=\n\r]+\s*\)",
            "[image removed]", response, flags=re.DOTALL)
        response = re.sub(r"data:image/[a-zA-Z0-9]+;base64,[A-Za-z0-9+/=\n\r]+",
            "[image removed]", response, flags=re.DOTALL)
        response = re.sub(r"<img[^>]+src=[\"']\s*data:image/[^\"']+[\"'][^>]*>",
            "[image removed]", response, flags=re.IGNORECASE | re.DOTALL)

        # Extract code block
        code_blocks = re.findall(r"```(?:python)?\s*(.*?)```", response, re.DOTALL)

        forbidden_patterns = [
            r"\bimport\s+(os|sys|subprocess|shlex)\b",
            r"\bopen\s*\(",
            r"__import__\(",
            r"\beval\s*\(",
            r"\bexec\s*\("
        ]
        chart_indicators = [
            r"\b(ax|plt)\.(plot|bar|pie|scatter|hist|imshow|boxplot|stackplot|fill_between)\b"
        ]

        selected_code_block = None
        for block in code_blocks:
            clean_block = block.strip()
            if any(re.search(pat, clean_block) for pat in forbidden_patterns):
                continue
            if any(re.search(ind, clean_block) for ind in chart_indicators):
                selected_code_block = re.sub(r"plt\.show\(\)", "", clean_block).strip()
                break

        # Clean explanation
        if selected_code_block:
            explanation = re.sub(r"```(?:python)?\s*" + re.escape(selected_code_block) + r"\s*```", "", response, flags=re.DOTALL).strip()
        else:
            explanation = response

        result = {
            "code_block": selected_code_block,
            "explanation": explanation,
            "status": "success" if selected_code_block else "no_code_generated",
            "data": parsed_data,
            "warnings": warnings,
        }

        self._latest_result = result
        return json.dumps(result)

    def _arun(self, user_input: str):
        raise NotImplementedError("Async operation not supported for ChartTool")
