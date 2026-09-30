"""
Map rendering.
"""
import contextlib
import io
import re

import matplotlib.pyplot as plt
import matplotlib.patheffects as patheffects
import numpy as np
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

    MIN_FIGSIZE_INCHES = (12.0, 7.0)

    @staticmethod
    def _ensure_min_figsize(fig) -> None:
        """Enlarge undersized LLM figures so choropleths remain readable."""
        min_w, min_h = MapRenderer.MIN_FIGSIZE_INCHES
        w, h = fig.get_size_inches()
        if w < min_w or h < min_h:
            fig.set_size_inches(max(w, min_w), max(h, min_h), forward=True)

    @staticmethod
    def _primary_geodataframe(ns: dict):
        if gpd is None:
            return None
        for key in ("merged", "gdf"):
            obj = ns.get(key)
            if obj is not None and hasattr(obj, "geometry") and hasattr(obj, "total_bounds"):
                if getattr(obj, "empty", False) or len(obj) == 0:
                    continue
                return obj
        return None

    @staticmethod
    def _tight_geometry_bounds(gdf):
        """
        Bounds of the main geometry cluster, ignoring far outliers.

        Data Commons state GeoJSON already insets Alaska/Hawaii beside the
        lower 48. A single stray coordinate (or true-geographic territory)
        still expands matplotlib's axes so the country looks tiny.
        """
        try:
            valid = gdf.geometry.notna() & ~gdf.geometry.is_empty
            g = gdf.loc[valid]
            if g.empty:
                return None
            pts = g.geometry.representative_point()
            xs = np.asarray(pts.x, dtype=float)
            ys = np.asarray(pts.y, dtype=float)
        except Exception:
            return None
        ok = np.isfinite(xs) & np.isfinite(ys)
        if int(ok.sum()) < 1:
            return None
        xs, ys = xs[ok], ys[ok]
        g = g.iloc[np.flatnonzero(ok)]
        if float(np.nanmax(np.abs(xs))) <= 180 and float(np.nanmax(np.abs(ys))) <= 90:
            conus = (xs >= -125.0) & (xs <= -66.0) & (ys >= 24.0) & (ys <= 50.0)
            if int(conus.sum()) >= 8:
                try:
                    minx, miny, maxx, maxy = g.iloc[np.flatnonzero(conus)].total_bounds
                except Exception:
                    minx = None
                if minx is not None and maxx > minx and maxy > miny:
                    pad_x = max((maxx - minx) * 0.05, 0.4)
                    pad_y = max((maxy - miny) * 0.05, 0.3)
                    return (minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y)
        mx, my = float(np.median(xs)), float(np.median(ys))
        dist = np.sqrt((xs - mx) ** 2 + (ys - my) ** 2)
        order = np.argsort(dist)
        core_n = max(3, int(np.ceil(0.7 * len(dist))))
        core = g.iloc[order[:core_n]]
        try:
            cminx, cminy, cmaxx, cmaxy = core.total_bounds
        except Exception:
            return None
        wx, wy = max(cmaxx - cminx, 1e-6), max(cmaxy - cminy, 1e-6)
        # Keep nearby insets (DC moves AK/HI beside CONUS) but drop far outliers.
        exp = (cminx - wx, cminy - wy, cmaxx + wx, cmaxy + wy)
        keep = (xs >= exp[0]) & (xs <= exp[2]) & (ys >= exp[1]) & (ys <= exp[3])
        try:
            minx, miny, maxx, maxy = g.iloc[np.flatnonzero(keep)].total_bounds
        except Exception:
            return None
        if not all(np.isfinite([minx, miny, maxx, maxy])) or maxx <= minx or maxy <= miny:
            return None
        pad_x = max((maxx - minx) * 0.05, (maxx - minx) * 0.01 + 1e-6)
        pad_y = max((maxy - miny) * 0.05, (maxy - miny) * 0.01 + 1e-6)
        return (minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y)

    @staticmethod
    def _is_map_axis(ax, bounds) -> bool:
        """True when this axes is showing the choropleth, not a colorbar."""
        minx, miny, maxx, maxy = bounds
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        if x1 < minx or x0 > maxx or y1 < miny or y0 > maxy:
            return False
        # Colorbar value ranges are tiny compared with geographic/projected extents.
        span = abs(x1 - x0)
        data_span = abs(maxx - minx)
        return span >= data_span * 0.25

    @staticmethod
    def _fit_map_view(fig, ns: dict) -> bool:
        """Crop map axes to the main geometry cluster and lock equal aspect to the box."""
        gdf = MapRenderer._primary_geodataframe(ns)
        if gdf is None:
            return False
        bounds = MapRenderer._tight_geometry_bounds(gdf)
        if bounds is None:
            return False
        minx, miny, maxx, maxy = bounds
        fitted = False
        for ax in fig.get_axes():
            if not MapRenderer._is_map_axis(ax, bounds):
                continue
            ax.set_xlim(minx, maxx)
            ax.set_ylim(miny, maxy)
            ax.set_aspect("equal", adjustable="box")
            fitted = True
        return fitted

    @staticmethod
    def _display_figure(fig) -> None:
        """Crop whitespace and show a PNG. st.pyplot keeps empty axes from equal-aspect + stretch."""
        buf = io.BytesIO()
        fig.savefig(
            buf,
            format="png",
            dpi=160,
            bbox_inches="tight",
            pad_inches=0.2,
            facecolor="white",
        )
        buf.seek(0)
        try:
            st.image(buf, width="stretch")
        except TypeError:
            try:
                st.image(buf, use_container_width=True)
            except TypeError:
                st.image(buf)

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
                self._ensure_min_figsize(fig)
                self._fit_map_view(fig, exec_globals)
                self._display_figure(fig)
                plt.close(fig)
                with st.expander("Map code", expanded=False):
                    st.code(clean_code, language="python")
            else:
                st.warning("No map figure was detected in the generated code.")
                with st.expander("Map code", expanded=True):
                    st.code(clean_code, language="python")

        except Exception as e:
            st.error(f"Error running map code: {e}")

