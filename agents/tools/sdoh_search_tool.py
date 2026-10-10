from __future__ import annotations

from typing import Any, Dict, List, Optional

import json
import re
import urllib.parse
import urllib.request

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from tools.cdc_places_helpers import search_catalog as search_cdc_places_catalog
from tools.sdoh_search_merge import interleave_search_results, per_source_cap


class PlaceScope(BaseModel):
    level: Optional[str] = Field(
        default=None,
        description="Optional place level hint (e.g., state, county, city). Used for ranking/filtering only.",
    )
    within: Optional[str] = Field(
        default=None,
        description=(
            "Optional human-readable place for Data Commons search (e.g., 'Kentucky', "
            "'Clermont County, OH', 'United States'). Never pass a DCID. Defaults to "
            "the United States when omitted."
        ),
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
        description="Optional allowlist of sources to search. Defaults to ['datacommons','cms','cdcplaces'].",
    )
    max_results: int = Field(default=20, description="Maximum number of candidates to return.")


def _safe_lower(x: Any) -> str:
    return str(x).strip().lower()


# Latest datacommons-mcp / Agent API search is place-scoped. Human-readable names only
# (not DCIDs). United States is the product default so SDoH discovery stays US-relevant.
_DEFAULT_DC_SEARCH_PLACES = ["United States"]


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


def _first_dict(d: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):
            return v
    return {}


def _table_rows_as_dicts(table: Any) -> List[Dict[str, Any]]:
    """Convert Agent API {columns, rows} tables into list[dict]."""
    if not isinstance(table, dict):
        return []
    cols = table.get("columns")
    rows = table.get("rows")
    if not isinstance(cols, list) or not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        item: Dict[str, Any] = {}
        for i, col in enumerate(cols):
            if i >= len(row) or not isinstance(col, str) or not col:
                continue
            item[col] = row[i]
        if item:
            out.append(item)
    return out


def _member_variable_dcids(topic: Dict[str, Any]) -> List[str]:
    members = topic.get("memberVariables")
    if members is None:
        members = topic.get("member_variables")
    if isinstance(members, dict):
        members = members.get("value") or members.get("values")
    if not isinstance(members, list):
        return []
    dcids: List[str] = []
    for m in members:
        if isinstance(m, str) and m.strip():
            dcids.append(m.strip())
        elif isinstance(m, dict):
            dcid = _coalesce(m, ["dcid", "DCID", "id"])
            if isinstance(dcid, str) and dcid.strip():
                dcids.append(dcid.strip())
    return dcids


def dc_search_places(place_scope: Optional[PlaceScope]) -> List[str]:
    """Human-readable places for MCP search_indicators (never DCIDs)."""
    if place_scope is not None:
        within = getattr(place_scope, "within", None)
        if isinstance(within, str) and within.strip():
            return [within.strip()]
    return list(_DEFAULT_DC_SEARCH_PLACES)


class SdohSearchTool(StructuredTool):
    """
    Unified indicator search facade for SDoH data.

    Data Commons via MCP search_indicators; CMS via data.cms.gov data.json catalog;
    CDC PLACES via Socrata measure index on data.cdc.gov.
    """

    def __init__(self, dc_search_tool: StructuredTool, dc_observations_tool: Optional[StructuredTool] = None) -> None:
        # StructuredTool is a pydantic model; set custom attrs via object.__setattr__
        # so they aren't dropped/blocked by pydantic's attribute handling.
        super().__init__(
            name="search_sdoh_indicators",
            description=(
                "Search for SDoH-related indicators across sources. Checks Data Commons first, "
                "then CDC PLACES (Socrata measure catalog). Returns candidates with name, source, "
                "native_id, indicator_id, type, repository, and metric_source (when available). "
                "When presenting results to the user, include those fields (e.g. Markdown table)—not IDs alone."
            ),
            args_schema=SearchSDoHIndicatorsInput,
            func=self._run,
        )
        object.__setattr__(self, "_dc_search_tool", dc_search_tool)
        object.__setattr__(self, "_dc_observations_tool", dc_observations_tool)
        object.__setattr__(self, "_cms_catalog_cache", None)

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
            src_meta = raw.get("sourceMetadata")
        if not isinstance(src_meta, dict):
            return None

        # Some series return placeholders like {"source_id":"unknown"} when metadata is missing.
        import_name = src_meta.get("import_name") or src_meta.get("importName")
        source_id = src_meta.get("source_id") or src_meta.get("sourceId")
        provenance_url = src_meta.get("provenance_url") or src_meta.get("provenanceUrl")
        if not import_name and not provenance_url and (source_id in (None, "", "unknown")):
            return None

        return {
            "import_name": import_name,
            "source_id": source_id,
            "measurement_method": src_meta.get("measurement_method") or src_meta.get("measurementMethod"),
            "observation_period": src_meta.get("observation_period") or src_meta.get("observationPeriod"),
            "provenance_url": provenance_url,
        }

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

    def _call_dc_search(
        self,
        query: str,
        include_topics: bool = True,
        places: Optional[List[str]] = None,
    ) -> Any:
        """
        Call Data Commons MCP search tool with best-effort arg mapping.
        We keep this resilient because the MCP tool schema is external to this repo.
        """
        place_names = [p.strip() for p in (places or []) if isinstance(p, str) and p.strip()]
        attempts: List[Dict[str, Any]] = []
        # Current datacommons-mcp: query + optional places (human-readable) + include_topics.
        scoped = {"query": query, "include_topics": bool(include_topics)}
        if place_names:
            scoped["places"] = place_names
        attempts.append(scoped)
        attempts.extend(
            [
                {"query": query, "include_topics": bool(include_topics)},
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

        Accepts current Agent API payloads (variableCandidates tables, or
        variables + dcidNameMappings), the older variables + dcid_name_mappings
        object list, and generic list[dict] payloads.
        """
        items: List[Dict[str, Any]] = []

        # MCP tool returns a JSON string today; accept both dict and JSON-string.
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                # If it's not JSON, we can't reliably normalize it.
                return []

        variable_rows: List[Dict[str, Any]] = []
        topic_rows: List[Dict[str, Any]] = []
        name_map: Dict[str, Any] = {}

        if isinstance(raw, dict):
            name_map = _first_dict(raw, ["dcid_name_mappings", "dcidNameMappings"])
            variable_rows.extend(
                _table_rows_as_dicts(
                    raw.get("variableCandidates") or raw.get("variable_candidates")
                )
            )
            topic_rows.extend(
                _table_rows_as_dicts(
                    raw.get("topicCandidates") or raw.get("topic_candidates")
                )
            )
            variables = raw.get("variables")
            if isinstance(variables, list):
                for v in variables:
                    if isinstance(v, dict):
                        variable_rows.append(v)
                    elif isinstance(v, str) and v.strip():
                        variable_rows.append({"dcid": v.strip()})
            topics = raw.get("topics")
            if isinstance(topics, list):
                topic_rows.extend([t for t in topics if isinstance(t, dict)])
            if not variable_rows and not topic_rows:
                for k in ["results", "items", "indicators", "data"]:
                    v = raw.get(k)
                    if isinstance(v, list):
                        raw = v
                        break

        seen: set[str] = set()
        limit = max_results or 20

        def _append_variable(dcid: Any, name: Any, description: Any = None, typ: Any = "StatisticalVariable") -> None:
            if not dcid or not isinstance(dcid, str):
                return
            dcid = dcid.strip()
            if not dcid or dcid in seen or dcid.startswith("dc/topic/"):
                return
            seen.add(dcid)
            mapped = name_map.get(dcid)
            desc = description
            if isinstance(desc, list) and desc:
                desc = str(desc[0])
            elif desc is not None:
                desc = str(desc)
            items.append(
                {
                    "indicator_id": f"datacommons:{dcid}",
                    "source": "datacommons",
                    "native_id": dcid,
                    "name": mapped or name or dcid,
                    "type": typ or "StatisticalVariable",
                    "description": desc,
                    "repository": {"name": "Data Commons"},
                    "metric_source": None,
                }
            )

        for v in variable_rows:
            dcid = _coalesce(v, ["dcid", "DCID", "id"])
            name = _coalesce(v, ["name", "Name", "title", "label"])
            alt_desc = _coalesce(v, ["alternate_descriptions", "alternateDescriptions", "description"])
            _append_variable(dcid, name, alt_desc)
            if len(items) >= limit:
                break

        if len(items) < limit:
            for topic in topic_rows:
                for member in _member_variable_dcids(topic):
                    _append_variable(member, None)
                    if len(items) >= limit:
                        break
                if len(items) >= limit:
                    break

        if not items and isinstance(raw, list):
            for r in raw:
                if not isinstance(r, dict):
                    continue
                dcid = _coalesce(r, ["dcid", "DCID", "id", "stat_var", "statVar", "statisticalVariable"])
                name = _coalesce(r, ["name", "Name", "title", "label"])
                typ = _coalesce(r, ["type", "Type"])
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
                if len(items) >= limit:
                    break

        items = items[:limit]

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

    _CMS_DATA_JSON_URL = "https://data.cms.gov/data.json"
    _CMS_ID_RE = re.compile(r"/dataset/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/")

    def _load_cms_catalog(self) -> List[Dict[str, Any]]:
        """
        Load CMS dataset catalog from Project Open Data `data.json`.

        Note: CMS previously exposed Socrata SODA /resource endpoints, but many of those now
        return HTTP 410. The `data.json` catalog currently points to the supported data-api/v1
        dataset UUIDs, which we use as stable CMS measure identifiers.
        """
        cached = getattr(self, "_cms_catalog_cache", None)
        if isinstance(cached, list):
            return cached

        req = urllib.request.Request(
            self._CMS_DATA_JSON_URL,
            headers={"Accept": "application/json", "User-Agent": "SDoH-Public-Data-Assistant/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        datasets = payload.get("dataset")
        if not isinstance(datasets, list):
            datasets = []

        object.__setattr__(self, "_cms_catalog_cache", datasets)
        return datasets

    def _extract_cms_dataset_uuid(self, d: Dict[str, Any]) -> Optional[str]:
        ident = d.get("identifier")
        if isinstance(ident, str):
            m = self._CMS_ID_RE.search(ident)
            if m:
                return m.group(1)
        # Fallback: try any distribution accessURL patterns
        dist = d.get("distribution")
        if isinstance(dist, list):
            for x in dist:
                if not isinstance(x, dict):
                    continue
                for k in ("accessURL", "resourcesAPI", "downloadURL"):
                    v = x.get(k)
                    if isinstance(v, str):
                        m = self._CMS_ID_RE.search(v)
                        if m:
                            return m.group(1)
        return None

    def _score_cms_dataset(self, d: Dict[str, Any], terms: List[str], query: str) -> int:
        hay = " ".join(
            [
                str(d.get("title") or ""),
                str(d.get("description") or ""),
                " ".join([str(x) for x in (d.get("keyword") or []) if isinstance(x, (str, int, float))]),
                " ".join([str(x) for x in (d.get("theme") or []) if isinstance(x, (str, int, float))]),
            ]
        ).lower()
        title = str(d.get("title") or "").strip().lower()
        q = str(query or "").strip().lower()
        score = 0
        # Strongly prefer near-exact title matches so small max_results still finds the right dataset.
        if q and title:
            if q == title:
                score += 100
            elif q in title:
                score += 60
        for t in terms:
            if t and t in hay:
                score += 3
        # Light boost for explicitly place-aggregated datasets.
        for geo_hint in ("county", "state", "zip", "hrr", "cbsa", "tract", "geography", "geographic"):
            if geo_hint in hay:
                score += 1
        return score

    def _cms_catalog_facts(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extra fields from Project Open Data catalog only (no inference).
        data.json does not expose per-column geography or upstream metric provenance;
        that appears only after fetching dataset schema or rows (e.g. get_sdoh_observations).
        """
        themes = d.get("theme")
        if not isinstance(themes, list):
            themes = [themes] if themes not in (None, "") else []
        themes = [str(x) for x in themes if x not in (None, "")]

        keywords = d.get("keyword")
        if not isinstance(keywords, list):
            keywords = [keywords] if keywords not in (None, "") else []
        keywords = [str(x) for x in keywords if x not in (None, "")]

        temporal = d.get("temporal")
        if temporal is None:
            dist = d.get("distribution")
            if isinstance(dist, list):
                for x in dist:
                    if isinstance(x, dict) and x.get("temporal"):
                        temporal = x.get("temporal")
                        break

        data_api_url: Optional[str] = None
        dist = d.get("distribution")
        if isinstance(dist, list):
            for x in dist:
                if not isinstance(x, dict):
                    continue
                fmt = str(x.get("format") or "").upper()
                url = x.get("accessURL")
                if fmt == "API" and isinstance(url, str) and "/data-api/v1/dataset/" in url:
                    data_api_url = url
                    break

        landing = d.get("landingPage")
        ident = d.get("identifier")

        out: Dict[str, Any] = {
            "themes": themes,
            "keywords": keywords,
            "temporal": temporal,
            "landing_page": landing if isinstance(landing, str) else None,
            "dataset_viewer_url": ident if isinstance(ident, str) else None,
            "data_api_url": data_api_url,
        }
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}

    def _search_cms(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        datasets = self._load_cms_catalog()
        # Tokenize query terms (very light; stable).
        terms = [t for t in re.split(r"[^a-zA-Z0-9]+", (query or "").lower()) if len(t) >= 3]
        scored: List[tuple[int, Dict[str, Any]]] = []
        for d in datasets:
            if not isinstance(d, dict):
                continue
            uuid = self._extract_cms_dataset_uuid(d)
            if not uuid:
                continue
            s = self._score_cms_dataset(d, terms, query=query)
            if s <= 0:
                continue
            scored.append((s, d))

        scored.sort(key=lambda x: x[0], reverse=True)
        out: List[Dict[str, Any]] = []
        for _, d in scored[: max_results or 20]:
            uuid = self._extract_cms_dataset_uuid(d)
            if not uuid:
                continue
            item: Dict[str, Any] = {
                "indicator_id": f"cms:{uuid}",
                "source": "cms",
                "native_id": uuid,
                "name": d.get("title") or uuid,
                "type": "CMSDataset",
                "description": d.get("description"),
                "repository": {"name": "CMS"},
                "metric_source": None,  # must remain null unless CMS provides explicit dataset source metadata
            }
            extra = self._cms_catalog_facts(d)
            if extra:
                item["catalog_metadata"] = extra
            out.append(item)
        return out

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
        allowed = [s.lower() for s in (sources or ["datacommons", "cms", "cdcplaces"])]
        warnings: List[str] = []
        sources_checked: List[str] = []
        fetch_sources = [s for s in allowed if s in ("datacommons", "cms", "cdcplaces")]
        per_cap = per_source_cap(max_results or 20, len(fetch_sources))
        buckets: List[List[Dict[str, Any]]] = []

        if len(fetch_sources) > 1:
            warnings.append(
                f"Multi-source search: up to {per_cap} candidates per source, interleaved in results "
                f"(max_results={max_results or 20} total). Increase max_results if you need more per repository."
            )

        # Data Commons. Time scope reserved for ranking later; place_scope.within
        # is forwarded as a human-readable search place (default: United States).
        if "datacommons" in allowed:
            sources_checked.append("datacommons")
            places = dc_search_places(place_scope)
            try:
                raw = self._call_dc_search(
                    query=query,
                    include_topics=include_topics,
                    places=places,
                )
                buckets.append(
                    self._normalize_dc_results(
                        raw,
                        max_results=per_cap,
                        include_metric_source=include_metric_source,
                        metric_source_probe_place_dcids=metric_source_probe_place_dcids,
                    )
                )
            except Exception as e:
                warnings.append(
                    f"Data Commons indicator search failed (best-effort): {type(e).__name__}: {e}"
                )
                buckets.append([])
            else:
                used_default_place = places == _DEFAULT_DC_SEARCH_PLACES and not (
                    place_scope and getattr(place_scope, "within", None)
                )
                if used_default_place:
                    warnings.append(
                        "Data Commons search scoped to 'United States' by default. "
                        "Pass place_scope.within with a human-readable place to check another geography."
                    )

        if "cms" in allowed:
            sources_checked.append("cms")
            try:
                buckets.append(self._search_cms(query=query, max_results=per_cap))
            except Exception as e:
                warnings.append(f"CMS indicator search failed (best-effort): {type(e).__name__}: {e}")
                buckets.append([])
        if "cdcplaces" in allowed:
            sources_checked.append("cdcplaces")
            try:
                scope_level = place_scope.level if place_scope and place_scope.level else None
                buckets.append(
                    search_cdc_places_catalog(
                        query=query,
                        max_results=per_cap,
                        place_scope_level=scope_level,
                    )
                )
            except Exception as e:
                warnings.append(f"CDC PLACES indicator search failed (best-effort): {type(e).__name__}: {e}")
                buckets.append([])
        unsupported = [s for s in allowed if s not in ("datacommons", "cms", "cdcplaces")]
        for s in unsupported:
            warnings.append(f"Source {s!r} is not supported (supported: datacommons, cms, cdcplaces).")

        # Time scope reserved for ranking later; keep the arg to lock the tool signature.
        _ = time_scope

        results = interleave_search_results(buckets, max_results or 20)

        return {
            "results": results,
            "sources_checked": sources_checked,
            "warnings": warnings,
        }

