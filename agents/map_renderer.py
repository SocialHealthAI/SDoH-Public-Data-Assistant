"""
Map rendering.
"""
import contextlib
import io
import re

import matplotlib.pyplot as plt
import matplotlib.patheffects as patheffects
import streamlit as st

try:
    import geopandas as gpd  # type: ignore
except Exception:  # geopandas is optional at runtime
    gpd = None  # type: ignore

try:
    import pandas as pd  # type: ignore
except Exception:  # pandas is optional at runtime
    pd = None  # type: ignore


class MapRenderer:
    """Handles map rendering from generated code."""

    @staticmethod
    def _strip_problematic_geojson_assignments(code: str) -> str:
        """
        Strip any generated code blocks that attempt to define large GeoJSON literals
        (e.g. GEOJSON = {...}) or reassign the injected GEOJSON_DATA.

        This is a best-effort line-based stripper that handles multi-line dict literals
        by tracking brace depth.
        """
        names = {"GEOJSON_DATA", "GEOJSON_OUTLINE", "GEOJSON", "GEODATA", "geojson_data"}
        lines = code.splitlines()
        out: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if m and m.group(1) in names:
                # Skip the assignment block. Track braces to handle multi-line dicts.
                depth = 0
                # Count braces on the first line too.
                depth += line.count("{") - line.count("}")
                i += 1
                while i < len(lines) and depth > 0:
                    depth += lines[i].count("{") - lines[i].count("}")
                    i += 1
                # Also skip any immediately following blank lines.
                while i < len(lines) and lines[i].strip() == "":
                    i += 1
                continue

            out.append(line)
            i += 1

        return "\n".join(out)

    @staticmethod
    def _rewrite_from_features_calls(code: str) -> str:
        """
        Force from_features to use injected collections. Calls that already use
        GEOJSON_OUTLINE are left unchanged; all other from_features(...) become
        GEOJSON_DATA["features"].
        """

        def repl(match) -> str:
            inner = match.group(1)
            if "GEOJSON_OUTLINE" in inner:
                return match.group(0)
            return 'gpd.GeoDataFrame.from_features(GEOJSON_DATA["features"])'

        return re.sub(
            r"gpd\.GeoDataFrame\.from_features\(([^)]*)\)",
            repl,
            code,
        )

    def render_from_code(
        self,
        code_block,
        explanation=None,
        geojson_ref=None,
        outline_geojson_ref=None,
        data_variables=None,
    ):
        """
        Execute map code in a controlled namespace and display the resulting figure.
        The executed code is expected to create `fig, ax = plt.subplots(...)`.

        Geometry is not passed through the LLM. A `geojson_ref` resolves to
        `GEOJSON_DATA` (primary choropleth layer). Optional `outline_geojson_ref`
        resolves to `GEOJSON_OUTLINE` for parent-boundary overlays only.
        """
        if not code_block:
            st.info("No map code was generated in the response.")
            return

        st.subheader("🗺️ Map")

        if explanation:
            st.markdown(explanation)

        try:
            # 1. Start from a clean matplotlib state
            plt.close("all")

            # 2. Strip calls that would clear or finalize the figure before we render it
            clean_code = code_block.replace("plt.show()", "").replace("\nplt.close()", "")

            # 2b. Strip imports (runtime already provides plt/gpd/pd/patheffects)
            clean_code = re.sub(r"(?m)^\s*(from\s+\S+\s+import\s+.*|import\s+.+)\s*$", "", clean_code)

            # 2b2. Invalid LLM pattern: plt.matplotlib.patheffects (pyplot has no .matplotlib.patheffects)
            clean_code = clean_code.replace("plt.matplotlib.patheffects", "patheffects")

            # 2c. Strip any GeoJSON literal assignments and force from_features to use injected GeoJSON
            clean_code = self._strip_problematic_geojson_assignments(clean_code)
            clean_code = self._rewrite_from_features_calls(clean_code)

            # If the model tries to plot shapely geometry returned by unary_union.boundary,
            # it will be a LineString/Polygon (no .plot). Wrap it as a GeoSeries.
            clean_code = re.sub(
                r"(\b\w+\b)\.unary_union\.boundary\.plot\(",
                r"gpd.GeoSeries([\1.unary_union.boundary]).plot(",
                clean_code,
            )

            # 2d. Log the final sanitized code for debugging
            try:
                print("[MapRenderer DEBUG] Executing sanitized map code:\n", clean_code)
            except Exception:
                pass
            st.code(clean_code, language="python")

            # 3. Very small safety filter (MapTool should already enforce this)
            forbidden_snippets = ["import os", "import sys", "import subprocess", "eval(", "exec(", "open("]
            if any(snippet in clean_code for snippet in forbidden_snippets):
                st.error("Generated map code contained forbidden operations and was not executed.")
                return

            # 4. Prepare execution environment with preloaded libraries
            exec_globals = {
                "plt": plt,
                "patheffects": patheffects,
            }
            if gpd is not None:
                exec_globals["gpd"] = gpd
            if pd is not None:
                exec_globals["pd"] = pd
            geojson_data = None
            if geojson_ref and hasattr(st, "session_state"):
                try:
                    cache = st.session_state.get("geojson_cache", {})
                    geojson_data = cache.get(geojson_ref)
                except Exception:
                    geojson_data = None

            if geojson_data is None:
                st.error(
                    "Map geometry was not available in this session. "
                    "Ensure get_geojson_for_places returned a valid geojson_ref "
                    "and that you are rendering within the same Streamlit session."
                )
                return

            exec_globals["GEOJSON_DATA"] = geojson_data

            if outline_geojson_ref:
                outline_data = None
                if hasattr(st, "session_state"):
                    try:
                        cache = st.session_state.get("geojson_cache", {})
                        outline_data = cache.get(outline_geojson_ref)
                    except Exception:
                        outline_data = None
                if outline_data is None:
                    st.warning(
                        "Outline geometry was not found in this session (outline_geojson_ref). "
                        "The map will run with an empty outline layer."
                    )
                    outline_data = {"type": "FeatureCollection", "features": []}
                exec_globals["GEOJSON_OUTLINE"] = outline_data

            # Inject parsed data variables (e.g. dcid, obesity_percent_2021) if provided
            if isinstance(data_variables, dict):
                for k, v in data_variables.items():
                    # Only simple identifier keys
                    if isinstance(k, str) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
                        exec_globals[k] = v

            # 5. Execute the code so that variables (including `fig`) end up in exec_globals
            with contextlib.redirect_stdout(io.StringIO()):
                exec(clean_code, exec_globals, exec_globals)

            # 6. Prefer explicit `fig` from the executed code, otherwise fall back to plt.gcf()
            fig = exec_globals.get("fig")
            if fig is None:
                fig = plt.gcf()

            if fig and fig.get_axes():
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.warning("No map figure was detected in the generated code.")

        except Exception as e:
            st.error(f"Error running map code: {e}")

