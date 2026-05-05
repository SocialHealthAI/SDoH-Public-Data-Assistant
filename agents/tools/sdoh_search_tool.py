from __future__ import annotations

from typing import Any, Dict, List, Optional

import json

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field


class PlaceScope(BaseModel):
    level: Optional[str] = Field(
        default=None,
        description="Optional place level hint (e.g., state, county, city). Used for ranking/filtering only.",
    )
    within: Optional[str] = Field(
        default=None,
        description="Optional parent place hint (e.g., 'Kentucky', 'Clermont County, OH'). Used for ranking/filtering only.",
    )


class TimeScope(BaseModel):
    year: Optional[int] = Field(default=None, description="Optional single year of interest.")
    years: Optional[List[int]] = Field(default=None, description="Optional list of years of interest.")


class SearchSDoHIndicatorsInput(BaseModel):
    query: str = Field(..., description="Indicator search text (e.g., 'obesity', 'below poverty', 'population').")
    place_scope: Optional[PlaceScope] = Field(default=None, description="Optional place scope for ranking/filtering.")
    time_scope: Optional[TimeScope] = Field(default=None, description="Optional time scope for ranking/filtering.")
    include_topics: bool = Field(
        default=True,
        description=(
            "Whether to include topic-backed expansion from the underlying Data Commons search. "
            "Defaults to true to maximize recall and align with the previous Data Commons tool usage."
        ),
    )
    include_metric_source: bool = Field(
        default=True,
        description=(
            "If true, attempts to populate metric_source (dataset/survey/model) by probing the "
            "Data Commons observations metadata for a small number of top candidates. This adds "
            "latency but provides accurate upstream source names (e.g., CDC500_States, ACS)."
        ),
    )
    metric_source_probe_place_dcids: List[str] = Field(
        default_factory=lambda: ["geoId/21", "geoId/06", "geoId/48", "country/USA"],
        description=(
            "Place DCIDs to try (in order) when probing Data Commons observations metadata to infer "
            "metric_source. This improves the chance of finding a series that exists for at least one "
            "common geography (e.g., state-level CDC PLACES)."
        ),
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="Optional allowlist of sources to search. Defaults to ['datacommons','cms','ihme'].",
    )
    max_results: int = Field(default=20, description="Maximum number of candidates to return.")


def _safe_lower(x: Any) -> str:
    return str(x).strip().lower()


def _coalesce(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    # case-insensitive lookup
    lower_map = {_safe_lower(k): k for k in d.keys()}
    for k in keys:
        lk = _safe_lower(k)
        if lk in lower_map:
            v = d.get(lower_map[lk])
            if v not in (None, ""):
                return v
    return None


class SdohSearchTool(StructuredTool):
    """
    Unified indicator search facade for SDoH data.

    Step 1: Data Commons-backed only (wraps existing MCP `search_indicators` tool),
    with CMS/IHME stubbed out for iterative rollout.
    """

    def __init__(self, dc_search_tool: StructuredTool, dc_observations_tool: Optional[StructuredTool] = None) -> None:
        # StructuredTool is a pydantic model; set custom attrs via object.__setattr__
        # so they aren't dropped/blocked by pydantic's attribute handling.
        super().__init__(
            name="search_sdoh_indicators",
            description=(
                "Search for SDoH-related indicators across sources. Checks Data Commons first, "
                "then CMS and IHME (stubs in current version). Returns candidates with source, "
                "native_id, display name, and repository/metric_source where available."
            ),
            args_schema=SearchSDoHIndicatorsInput,
            func=self._run,
        )
        object.__setattr__(self, "_dc_search_tool", dc_search_tool)
        object.__setattr__(self, "_dc_observations_tool", dc_observations_tool)

    def _call_dc_observation_metadata(self, variable_dcid: str, place_dcid: str) -> Optional[Dict[str, Any]]:
        tool = getattr(self, "_dc_observations_tool", None)
        if tool is None:
            return None

        try:
            raw = tool.invoke({"variable_dcid": variable_dcid, "place_dcid": place_dcid, "date": "latest"})
        except Exception:
            return None

        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return None

        if not isinstance(raw, dict):
            return None

        src_meta = raw.get("source_metadata")
        if not isinstance(src_meta, dict):
            return None

        # Some series return placeholders like {"source_id":"unknown"} when metadata is missing.
        import_name = src_meta.get("import_name")
        source_id = src_meta.get("source_id")
        provenance_url = src_meta.get("provenance_url")
        if not import_name and not provenance_url and (source_id in (None, "", "unknown")):
            return None

        return src_meta

    def _infer_metric_source(self, variable_dcid: str, probe_places: List[str]) -> Optional[Dict[str, Any]]:
        for place in probe_places:
            meta = self._call_dc_observation_metadata(variable_dcid, place)
            if meta:
                return {
                    "name": meta.get("import_name") or meta.get("source_id"),
                    "import_name": meta.get("import_name"),
                    "source_id": meta.get("source_id"),
                    "measurement_method": meta.get("measurement_method"),
                    "observation_period": meta.get("observation_period"),
                    "url": meta.get("provenance_url"),
                    "probe_place_dcid": place,
                }
        return None

    def _call_dc_search(self, query: str, include_topics: bool = True) -> Any:
        """
        Call Data Commons MCP search tool with best-effort arg mapping.
        We keep this resilient because the MCP tool schema is external to this repo.
        """
        # Try common parameter names for search text.
        attempts = []
        # Known datacommons-mcp schema uses "query" and supports include_topics.
        attempts.append({"query": query, "include_topics": bool(include_topics)})
        # Fallbacks for older/alternate schemas.
        attempts.extend(
            [
                {"query": query},
                {"q": query},
                {"text": query},
                {"search_term": query},
                {"term": query},
            ]
        )
        last_err: Optional[Exception] = None
        for kwargs in attempts:
            try:
                return self._dc_search_tool.invoke(kwargs)
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"Failed calling Data Commons search tool for query={query!r}: {last_err}")

    def _normalize_dc_results(
        self,
        raw: Any,
        max_results: int,
        include_metric_source: bool = True,
        metric_source_probe_place_dcids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Normalize Data Commons search results into the unified candidate shape.
        Accepts list[dict] or dict-with-list payloads; ignores unknown shapes.
        """
        items: List[Dict[str, Any]] = []

        # MCP tool returns a JSON string today; accept both dict and JSON-string.
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                # If it's not JSON, we can't reliably normalize it.
                return []

        # Raw may be a dict containing a list under various keys.
        if isinstance(raw, dict):
            # datacommons-mcp returns: {"variables":[{dcid,...}], "dcid_name_mappings":{...}, ...}
            dcid_name_mappings = raw.get("dcid_name_mappings") if isinstance(raw.get("dcid_name_mappings"), dict) else {}

            variables = raw.get("variables")
            if isinstance(variables, list):
                for v in variables:
                    if not isinstance(v, dict):
                        continue
                    dcid = _coalesce(v, ["dcid", "DCID", "id"])
                    if not dcid:
                        continue
                    name = dcid_name_mappings.get(dcid) or _coalesce(v, ["name", "Name", "title", "label"])
                    alt_desc = _coalesce(v, ["alternate_descriptions", "alternateDescriptions", "description"])
                    # alternate_descriptions is usually a list[str]
                    description = None
                    if isinstance(alt_desc, list) and alt_desc:
                        description = str(alt_desc[0])
                    elif isinstance(alt_desc, str):
                        description = alt_desc

                    items.append(
                        {
                            "indicator_id": f"datacommons:{dcid}",
                            "source": "datacommons",
                            "native_id": dcid,
                            "name": name or dcid,
                            "type": "StatisticalVariable",
                            "description": description,
                            # repository: where we retrieved the metric from
                            "repository": {"name": "Data Commons"},
                            # metric_source: upstream dataset/survey/model backing this metric (if known)
                            "metric_source": None,
                        }
                    )
                items = items[: max_results or 20]

                if include_metric_source:
                    # Probe a small number of candidates to infer dataset/survey backing the metric.
                    # This is best-effort and may be None if the series isn't available for probe place.
                    probe_places = metric_source_probe_place_dcids or ["geoId/21"]
                    filled = 0
                    target = min(5, len(items))
                    # Scan a bit deeper than the first N so we can skip candidates
                    # that have no observations for the probe places.
                    for i in range(min(len(items), 50)):
                        if filled >= target:
                            break
                        native_id = items[i].get("native_id")
                        if not native_id or not isinstance(native_id, str):
                            continue
                        ms = self._infer_metric_source(native_id, probe_places)
                        if not ms:
                            continue
                        items[i]["metric_source"] = ms
                        filled += 1

                return items

            for k in ["results", "items", "indicators", "data", "variables"]:
                v = raw.get(k)
                if isinstance(v, list):
                    raw = v
                    break

        if isinstance(raw, list):
            for r in raw:
                if not isinstance(r, dict):
                    continue
                dcid = _coalesce(r, ["dcid", "DCID", "id", "stat_var", "statVar", "statisticalVariable"])
                name = _coalesce(r, ["name", "Name", "title", "label"])
                typ = _coalesce(r, ["type", "Type"])
                # Some payloads may put dataset/source under "provenance" or "dataset".
                src = _coalesce(r, ["source", "Source", "dataset", "metric_source", "metricSource", "provenance"])

                if not dcid and not name:
                    continue

                items.append(
                    {
                        "indicator_id": f"datacommons:{dcid}" if dcid else f"datacommons:name:{name}",
                        "source": "datacommons",
                        "native_id": dcid,
                        "name": name or dcid,
                        "type": typ,
                        "repository": {"name": "Data Commons"},
                        "metric_source": {"name": src} if src else None,
                    }
                )

        items = items[: max_results or 20]

        if include_metric_source:
            probe_places = metric_source_probe_place_dcids or ["geoId/21"]
            filled = 0
            target = min(5, len(items))
            for i in range(min(len(items), 50)):
                if filled >= target:
                    break
                native_id = items[i].get("native_id")
                if not native_id or not isinstance(native_id, str):
                    continue
                ms = self._infer_metric_source(native_id, probe_places)
                if not ms:
                    continue
                items[i]["metric_source"] = ms
                filled += 1

        return items

    def _run(
        self,
        query: str,
        place_scope: Optional[PlaceScope] = None,
        time_scope: Optional[TimeScope] = None,
        include_topics: bool = True,
        include_metric_source: bool = True,
        metric_source_probe_place_dcids: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        allowed = [s.lower() for s in (sources or ["datacommons", "cms", "ihme"])]
        results: List[Dict[str, Any]] = []
        warnings: List[str] = []
        sources_checked: List[str] = []

        # Step 1: Data Commons only (real). Place/time scopes reserved for ranking later.
        if "datacommons" in allowed:
            sources_checked.append("datacommons")
            raw = self._call_dc_search(query=query, include_topics=include_topics)
            results.extend(
                self._normalize_dc_results(
                    raw,
                    max_results=max_results,
                    include_metric_source=include_metric_source,
                    metric_source_probe_place_dcids=metric_source_probe_place_dcids,
                )
            )

        # Step 1 stubs
        if "cms" in allowed:
            sources_checked.append("cms")
            warnings.append("CMS indicator search not implemented yet (stub).")
        if "ihme" in allowed:
            sources_checked.append("ihme")
            warnings.append("IHME indicator search not implemented yet (stub).")

        # Best-effort light filtering/ranking hooks (no-op for now; keep args to lock signature)
        _ = place_scope
        _ = time_scope

        return {
            "results": results[: max_results or 20],
            "sources_checked": sources_checked,
            "warnings": warnings,
        }

