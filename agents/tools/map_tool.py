from typing import Optional, Type, ClassVar, Any, Dict, List
import json
import re

from langchain.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage


class MapToolInput(BaseModel):
    """Input schema for the MapTool.

    The tool expects a `geojson_ref` key referencing geometry stored
    server-side in the current Streamlit session (returned by
    `GeoJsonTool`).     At execution time, the renderer resolves that key
    and injects the GeoJSON FeatureCollection into the code namespace
    as `GEOJSON_DATA`. Optional `outline_geojson_ref` injects `GEOJSON_OUTLINE`
    for parent-region boundaries only (no data merge on that layer).
    """

    user_input: str = Field(
        ...,
        description=(
            "Natural language description of the requested map. "
            "Example: 'Choropleth of obesity rates by US state with a legend and title.'"
        ),
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Structured data keyed by region identifier. "
            "Example: {'state_fips': ['01', '02'], 'obesity_rate': [30.2, 28.5]}. "
            "When you also call the GeoJsonTool to fetch geometry, you MUST use "
            "the same region identifiers here as the place DCIDs you pass to "
            "GeoJsonTool so that the tabular data can be joined correctly to "
            "the map features."
        ),
    )
    geojson_ref: Optional[str] = Field(
        None,
        description=(
            "Reference key for primary map geometry (choropleth layer) stored server-side. "
            "If provided, you MUST pass this value through unchanged and do "
            "not embed any GeoJSON in the generated code."
        ),
    )
    outline_geojson_ref: Optional[str] = Field(
        None,
        description=(
            "Optional second reference from get_geojson_for_places for a higher-level "
            "boundary only (e.g. county outline while primary layer is cities). "
            "Must be a separate tool call with the parent place DCID(s). "
            "Do not merge observation data into this layer; use for outline plotting only."
        ),
    )
    region_type: str = Field(
        "GENERIC",
        description=(
            "Optional semantic label describing what the regions represent, "
            "e.g. 'US_STATES', 'US_COUNTIES', 'WORLD'. This is only used to "
            "help describe the map in natural language; it is no longer used "
            "to load shapefiles from disk."
        ),
        )


class MapTool(BaseTool):
    """
    Generate geopandas-based map code (choropleths, etc.) from natural language.

    This tool mirrors ChartTool but focuses on GeoPandas + matplotlib maps.

    The tool does NOT fetch data or read files on its own; it only generates
    plotting code. You MUST pass actual data via the `data` parameter and a
    `geojson_ref` that points to primary geometry stored server-side in the current
    Streamlit session. Optionally pass `outline_geojson_ref` for a parent boundary layer.
    """

    name: ClassVar[str] = "generate_map"
    description: ClassVar[str] = (
        "Generate Python code using GeoPandas and matplotlib to render maps. "
        "Use this when the user asks for a choropleth or geographic map. "
        "The tool expects: (1) structured numeric data keyed by region identifier, "
        "(2) geojson_ref for the primary choropleth geometry (from get_geojson_for_places), "
        "and optionally (3) outline_geojson_ref for a higher-level outline from a second "
        "get_geojson_for_places call."
    )
    args_schema: ClassVar[Type[BaseModel]] = MapToolInput

    llm: object = Field(..., description="The LLM to use for map code generation")
    _map_prompt_template: PromptTemplate = PrivateAttr()
    _latest_result: dict = PrivateAttr(default=None)

    def __init__(self, llm: object, **kwargs):
        super().__init__(llm=llm, **kwargs)
        self._map_prompt_template = PromptTemplate.from_template(
            """
            You generate Python code that creates a geographic choropleth map using GeoPandas and matplotlib.

            The runtime environment already contains the following objects:

            - gpd  (GeoPandas)
            - pd   (Pandas)
            - plt  (matplotlib.pyplot)

            These libraries are already imported and available.

            You MUST NOT import any libraries.
            Attempting to import libraries will crash the runtime.

            --------------------------------------------------
            CRITICAL RUNTIME VARIABLES
            --------------------------------------------------

            A variable named exactly `GEOJSON_DATA` exists in the runtime.

            `GEOJSON_DATA` is a read-only GeoJSON FeatureCollection dictionary
            resolved server-side from the provided `geojson_ref`.

            Attempting to assign to or redefine `GEOJSON_DATA` will crash the program.

            You MUST NEVER:

            - assign to GEOJSON_DATA
            - create GEOJSON_DATA
            - create GEOJSON
            - create geojson_data
            - embed a FeatureCollection literal
            - parse geometry using json.loads or json.dumps

            The only valid way to access the primary (choropleth) geometry is:

            gdf = gpd.GeoDataFrame.from_features(GEOJSON_DATA["features"])

            {outline_layer_instruction}

            --------------------------------------------------
            MANDATORY FIRST LINE OF CODE
            --------------------------------------------------

            The FIRST executable line of your code MUST be exactly:

            gdf = gpd.GeoDataFrame.from_features(GEOJSON_DATA["features"])

            Do NOT place any code before this line.

            Do NOT assign to GEOJSON_DATA before or after this line.

            --------------------------------------------------
            MAP REQUIREMENTS
            --------------------------------------------------

            Your code must:

            1. Construct a GeoDataFrame from GEOJSON_DATA
            2. Convert the provided DATA variables into a pandas DataFrame
            3. Merge the DataFrame with the GeoDataFrame (see ROBUST MERGE below)
            4. Create a choropleth map
            5. Add a legend
            6. Add a title
            7. Hide axes

            If any input data lists have missing values (None/null/NaN) or mismatched lengths,
            your code MUST construct an aligned table and safely handle missing values so the
            code does not crash (e.g., drop rows with missing metric before plotting or let them
            render as missing on the choropleth).

            --------------------------------------------------
            ROBUST MERGE (use this so city/village outlines get data)
            --------------------------------------------------

            The GeoJSON features have both "dcid" and "dcid_norm" (dcid with "geoId/" stripped).
            Data Commons observation data may use "geoId/XXX" or bare "XXX". To avoid join
            failures and "no data" for most regions, ALWAYS normalize and merge on dcid_norm:

            - Add a normalized key to the data table: df["dcid_norm"] = df["dcid"].astype(str).str.strip().str.replace("geoId/", "", regex=False)
            - Merge on dcid_norm: merged = gdf.merge(df, on="dcid_norm", how="left")
            - Use "merged" (not gdf) for the choropleth plot so every geometry gets the correct value.

            Create the figure explicitly:

            fig, ax = plt.subplots(figsize=(10, 6))

            Plot the choropleth using GeoPandas:

            merged.plot(
                column=<metric_column>,
                ax=ax,
                legend=True
            )

            Add a title and hide axes:

            ax.set_title("<descriptive title>")
            ax.axis("off")

            --------------------------------------------------
            REGION HIERARCHY AND OVERLAYS
            --------------------------------------------------

            Region types are ordered from largest to smallest (coarse to fine). Use this
            to decide what to color, what to draw as outline, and what to label.

            Hierarchy (top = largest):
              1. Country
              2. State / Province / AdminRegion1
              3. County / District / AdminRegion2
              4. ZIP Code / ZCTA / PostalCode
              5. City / Town / Village / CensusDesignatedPlace / Place

            Overlay rules:
              - CHOROPLETH (fill/color): Apply to exactly one layer—the "primary" layer
                that has the metric data. Merge the data table with that layer's
                geometry and plot with merged.plot(column=<metric>, ...). Only one
                layer carries the color scale.
              - OUTLINES: Draw boundaries for the primary layer (optional) and/or for
                any HIGHER level in the hierarchy (parent regions). Example: if the
                primary layer is counties, draw state outlines on top; if the primary
                is cities, draw county outline and optionally state outline. Use
                facecolor="none" or transparent fill so only the boundary shows.
                Higher-level geometry must come from a separate get_geojson_for_places
                call when the user asks for a parent outline (e.g. "county map with
                state outline").

                ZIP note: ZIP codes do not always nest cleanly inside counties/states,
                so treat ZIP as an overlapping layer. You can still draw county/state
                outlines by requesting the parent geometries with get_geojson_for_places.
              - LABELS: Apply to the primary layer or any LOWER (finer) layer when it
                is visually useful. Example: if coloring counties, label county names;
                if coloring counties and city names are available, you may label cities.
                Place text at centroids or representative points; avoid overlapping text.

                ZIP note: ZIP labels can easily clutter; keep labels minimal or skip
                labels when there are many ZIPs.
              - NEVER embed geometry: Do not define GeoJSON or geometry literals in
                code. Use only the server-injected variable(s) (GEOJSON_DATA and,
                when provided, GEOJSON_OUTLINE). All geometry must come from
                get_geojson_for_places and be referenced by geojson_ref /
                outline_geojson_ref.

            Two-layer maps: When `outline_geojson_ref` is passed to this tool, the runtime
            provides both GEOJSON_DATA (primary) and GEOJSON_OUTLINE (parent/higher-level
            boundaries). Choropleth and data merge use GEOJSON_DATA only; draw outlines from
            GEOJSON_OUTLINE on top with facecolor="none".

            Single-layer maps: If no outline ref is provided, only GEOJSON_DATA exists.
            Color that layer; optionally emphasize its own boundaries; optionally add labels.

            --------------------------------------------------
            PROHIBITED OPERATIONS
            --------------------------------------------------

            Do NOT do any of the following:

            - import any modules
            - open files
            - read shapefiles from disk
            - write files
            - use os, sys, subprocess, or shlex
            - call eval() or exec()
            - call plt.show()
            - call plt.savefig()
            - call plt.close()

            --------------------------------------------------
            DATA SECTION
            --------------------------------------------------

            {data_instruction}

            You MUST use the variables exactly as defined above.

            Do NOT create new lists of region identifiers or metrics.
            Do NOT create placeholder or example data.
            Do NOT rename the variables.

            You may convert the variables into a pandas DataFrame before merging.

            --------------------------------------------------
            OUTPUT FORMAT
            --------------------------------------------------

            1) Begin with a short explanation describing what the map shows.

            2) Then output exactly ONE Python code block.

            The code block must begin exactly like this:

            ```python
            gdf = gpd.GeoDataFrame.from_features(GEOJSON_DATA["features"])

            User map request:
            {user_input}
            """
        )

    def _normalize_data(self, data: Dict[str, Any]) -> Optional[Dict[str, List]]:
        """
        Normalize various data formats into a consistent dict structure.
        Accepts either {'columns': [...], 'rows': [[...]]} or direct {key: [values]} format.
        """
        if not data or not isinstance(data, dict):
            return None

        if "columns" in data and "rows" in data:
            columns = data["columns"]
            rows = data["rows"]
            if not columns or not rows:
                return None

            result: Dict[str, List] = {str(col): [] for col in columns}
            for row in rows:
                for i, col in enumerate(columns):
                    if i < len(row):
                        result[str(col)].append(row[i])
            return result

        if all(isinstance(v, list) for v in data.values()):
            # Already normalized only if every column is the same length.
            # We MUST NOT pad by index here because map data must stay aligned by region identifier.
            lengths = [len(v) for v in data.values()]
            if not lengths or min(lengths) == 0:
                return None
            if len(set(lengths)) != 1:
                return None
            return data  # already normalized

        if "rows" in data and isinstance(data["rows"], list):
            try:
                rows = data["rows"]
                if rows and len(rows[0]) >= 2:
                    return {
                        "col_0": [r[0] for r in rows],
                        "col_1": [r[1] for r in rows],
                    }
            except Exception:
                pass

        return None

    def _format_data_for_prompt(self, parsed_data: Dict[str, List]) -> str:
        """Format parsed data as Python code snippet for the prompt."""
        lines: List[str] = []
        for key, values in parsed_data.items():
            py_key = re.sub(r"[^a-zA-Z0-9_]", "_", str(key))
            if py_key and py_key[0].isdigit():
                py_key = "col_" + py_key

            if all(isinstance(v, (int, float)) for v in values):
                lines.append(f"{py_key} = {values}")
            else:
                formatted_values = [
                    f"'{v}'" if isinstance(v, str) else str(v) for v in values
                ]
                lines.append(f"{py_key} = [{', '.join(formatted_values)}]")

        return "\n".join(lines)

    def _run(
        self,
        user_input: str,
        data: Optional[dict] = None,
        geojson_ref: Optional[str] = None,
        outline_geojson_ref: Optional[str] = None,
        region_type: str = "GENERIC",
    ) -> str:
        """
        Generate GeoPandas/matplotlib map code.

        Returns a JSON-stringified dict with keys:
        - code_block: the selected Python code block
        - explanation: natural language explanation of the map
        - status: "success" or "no_code_generated"
        - data: the parsed/normalized data used for the prompt
        - geojson_ref: reference key for primary geometry (required)
        - outline_geojson_ref: optional outline layer reference
        """

        parsed_data: Optional[Dict[str, List]] = None
        if data:
            parsed_data = self._normalize_data(data)

        if parsed_data:
            data_code = self._format_data_for_prompt(parsed_data)
            data_instruction = f"""
**IMPORTANT: YOU MUST USE THIS EXACT DATA IN YOUR CODE.**

```python
# Use this data exactly as provided - DO NOT create example or placeholder data.
{data_code}
```

The variable names above correspond to the input data columns.
You may construct a pandas or GeoPandas object from this data to join with the GeoDataFrame.
"""
        else:
            data_instruction = (
                "No structured data was provided. You may create small example "
                "data inline if absolutely necessary, but prefer real data via the "
                "'data' argument when available."
            )

        if not geojson_ref:
            result = {
                "code_block": None,
                "explanation": "Missing required geojson_ref. Call get_geojson_for_places first and pass its geojson_ref into generate_map.",
                "status": "error",
                "data": parsed_data,
                "geojson_ref": None,
                "outline_geojson_ref": None,
            }
            self._latest_result = result
            return json.dumps(result)

        geojson_note = (
            f"A geometry reference key is provided (geojson_ref={geojson_ref}). "
            "The runtime will resolve this server-side and provide a variable named exactly "
            "`GEOJSON_DATA` containing the GeoJSON FeatureCollection. You MUST "
            "NOT embed any GeoJSON in code and MUST build the GeoDataFrame via "
            "`gdf = gpd.GeoDataFrame.from_features(GEOJSON_DATA['features'])`."
        )
        if outline_geojson_ref:
            geojson_note += (
                f" A second outline reference is provided (outline_geojson_ref={outline_geojson_ref}). "
                "The runtime injects `GEOJSON_OUTLINE` for parent boundaries only—do not merge data into it."
            )

        if outline_geojson_ref:
            outline_layer_instruction = f"""
            --------------------------------------------------
            OUTLINE LAYER (secondary geometry — boundaries only)
            --------------------------------------------------

            An additional reference is active: outline_geojson_ref={outline_geojson_ref}.

            The runtime injects a read-only variable `GEOJSON_OUTLINE` (GeoJSON FeatureCollection).

            You MUST:
            - Keep the mandatory first line exactly as specified (build `gdf` from GEOJSON_DATA only).
            - On the very next line, build the outline GeoDataFrame:
              gdf_outline = gpd.GeoDataFrame.from_features(GEOJSON_OUTLINE["features"])
            - Merge observation data ONLY with `gdf` (then `merged`). NEVER merge metrics into `gdf_outline`.
            - Plot the choropleth from `merged` first, then overlay outlines, e.g.:
              gdf_outline.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=2.0, zorder=5)
            - You MUST NEVER assign to, redefine, or embed literals for GEOJSON_OUTLINE.

            If several outline features exist, you may dissolve for one clean boundary, e.g.:
              gdf_outline.dissolve().boundary.plot(ax=ax, color="black", linewidth=2.0, zorder=5)
            (Use gpd.GeoSeries([...]) if needed for shapely geometry .plot issues.)
            """
        else:
            outline_layer_instruction = ""

        query = self._map_prompt_template.format(
            user_input=f"{user_input}\n\nMap region_type (semantic only): {region_type}\n\n{geojson_note}",
            data_instruction=data_instruction,
            outline_layer_instruction=outline_layer_instruction,
        )

        response_msg = self.llm.invoke([HumanMessage(content=query)])
        response = response_msg.content.strip()

        response = re.sub(
            r"!\[.*?\]\(\s*data:image/[a-zA-Z0-9]+;base64,[A-Za-z0-9+/=\n\r]+\s*\)",
            "[image removed]",
            response,
            flags=re.DOTALL,
        )
        response = re.sub(
            r"data:image/[a-zA-Z0-9]+;base64,[A-Za-z0-9+/=\n\r]+",
            "[image removed]",
            response,
            flags=re.DOTALL,
        )
        response = re.sub(
            r"<img[^>]+src=[\"']\s*data:image/[^\"']+[\"'][^>]*>",
            "[image removed]",
            response,
            flags=re.IGNORECASE | re.DOTALL,
        )

        code_blocks = re.findall(r"```(?:python)?\s*(.*?)```", response, re.DOTALL)

        forbidden_patterns = [
            r"\bimport\s+(os|sys|subprocess|shlex)\b",
            r"\bopen\s*\(",
            r"__import__\(",
            r"\beval\s*\(",
            r"\bexec\s*\(",
        ]
        map_indicators = [
            r"\bgpd\.GeoDataFrame\.from_features\b",
            r"\.plot\(",
        ]

        selected_code_block: Optional[str] = None
        for block in code_blocks:
            clean_block = block.strip()
            if any(re.search(pat, clean_block) for pat in forbidden_patterns):
                continue
            if any(re.search(ind, clean_block) for ind in map_indicators):
                selected_code_block = re.sub(r"plt\.show\(\)", "", clean_block).strip()
                break

        # Fallback: some responses may not wrap code in ``` fences.
        # In that case, try to heuristically extract a code block starting
        # from the first 'import geopandas' line up to a 'Notes' section.
        if selected_code_block is None:
            start_match = re.search(r"\bimport\s+geopandas\b", response)
            if start_match:
                # Cut off any trailing narrative like "Notes and next steps"
                tail = response[start_match.start():]
                notes_match = re.search(r"\nNotes", tail)
                if notes_match:
                    candidate = tail[: notes_match.start()]
                else:
                    candidate = tail
                clean_candidate = candidate.strip()
                if clean_candidate and not any(
                    re.search(pat, clean_candidate) for pat in forbidden_patterns
                ):
                    selected_code_block = re.sub(
                        r"plt\.show\(\)", "", clean_candidate
                    ).strip()

        if selected_code_block:
            explanation = re.sub(
                r"```(?:python)?\s*" + re.escape(selected_code_block) + r"\s*```",
                "",
                response,
                flags=re.DOTALL,
            ).strip()
            status = "success"
        else:
            explanation = response
            status = "no_code_generated"

        # Include extra debugging info so the caller (and UI) can inspect
        # exactly what was generated and what we selected.
        result = {
            "code_block": selected_code_block,
            "explanation": explanation,
            "status": status,
            "data": parsed_data,
            "geojson_ref": geojson_ref,
            "outline_geojson_ref": outline_geojson_ref,
            "raw_response": response,
            "debug": {
                "had_fenced_block": bool(code_blocks),
                "num_fenced_blocks": len(code_blocks),
                "used_fallback_extraction": selected_code_block is not None
                and not code_blocks,
            },
        }

        # Temporary debug logging to stdout for tracing map generation behavior.
        # This will show up in the Streamlit/agent logs.
        try:
            print(
                "[MapTool DEBUG] status=",
                status,
                " code_block_len=",
                len(selected_code_block) if selected_code_block else 0,
                " fenced_blocks=",
                len(code_blocks),
            )
        except Exception:
            # Logging must never break tool behavior
            pass

        self._latest_result = result
        return json.dumps(result)

    def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async operation not supported for MapTool")

