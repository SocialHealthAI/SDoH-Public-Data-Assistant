from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from tools.dc_place_expand import expand_places_for_parent_and_level, normalize_place_key
from tools.dc_v2_helpers import dc_api_key, fetch_observations_by_entity_batch


PlaceLevel = Literal[
    "country",
    "state",
    "county",
    "city",
    "tract",
    "zip",
    "cbsa",
    "hsa",
    "other",
]

JoinType = Literal["inner", "left"]
OutputFormat = Literal["long", "wide"]


class PlaceRequest(BaseModel):
    level: PlaceLevel = Field(..., description="Geographic level of requested places.")
    ids: Optional[List[str]] = Field(
        default=None,
        description="Explicit place identifiers (DCIDs, FIPS, etc.). DC-backed implementation currently expects DCIDs or FIPS-like IDs.",
    )
    within: Optional[str] = Field(
        default=None,
        description=(
            "Optional parent (US state name/abbr like 'Indiana'/'IN', or a parent DCID e.g. geoId/39025). "
            "Expands to child place DCIDs via Data Commons v2 (requires DC_API_KEY)."
        ),
    )
    include_territories: Optional[bool] = Field(default=None, description="Whether to include territories (best-effort).")


class TimeRequest(BaseModel):
    year: Optional[int] = Field(default=None, description="Single year.")
    years: Optional[List[int]] = Field(default=None, description="Multiple years.")


class JoinRequest(BaseModel):
    attempt_join: bool = Field(default=True, description="Attempt to join when multiple indicators are requested.")
    join_keys: List[str] = Field(default_factory=lambda: ["place_key", "year"], description="Join keys (fixed).")
    join_type: JoinType = Field(default="inner", description="Join type.")


class OutputRequest(BaseModel):
    format: OutputFormat = Field(default="long", description="Output format: long or wide.")
    include_repository: bool = Field(default=True, description="Include repository info.")
    include_metric_source: bool = Field(default=True, description="Include metric_source info when available.")
    include_place_columns: bool = Field(default=True, description="Include place_name/place_level columns.")


class GetSDoHObservationsInput(BaseModel):
    indicators: List[str] = Field(..., description="List of indicator_id values from search_sdoh_indicators.")
    place: PlaceRequest = Field(..., description="Place request.")
    time: Optional[TimeRequest] = Field(default=None, description="Time request (required when multiple indicators).")
    join: Optional[JoinRequest] = Field(default=None, description="Join configuration.")
    output: Optional[OutputRequest] = Field(default=None, description="Output configuration.")
    sources: Optional[List[str]] = Field(default=None, description="Optional allowlist of sources.")


def _as_json_dict(x: Any) -> Optional[Dict[str, Any]]:
    if x is None:
        return None
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            v = json.loads(x)
            return v if isinstance(v, dict) else None
        except Exception:
            return None
    return None


_YEAR_RE = re.compile(r"^\s*(\d{4})\s*$")


def _normalize_year(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        m = _YEAR_RE.match(raw)
        if m:
            return int(m.group(1))
    return None


def _parse_indicator_id(indicator_id: str) -> Tuple[str, str]:
    """
    Returns (source, native_id). Defaults to datacommons if no prefix found.
    """
    s = str(indicator_id).strip()
    if ":" in s:
        prefix, rest = s.split(":", 1)
        return prefix.strip().lower(), rest.strip()
    return "datacommons", s


def _coalesce(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    lower_map = {str(k).strip().lower(): k for k in d.keys()}
    for k in keys:
        lk = str(k).strip().lower()
        if lk in lower_map:
            v = d.get(lower_map[lk])
            if v not in (None, ""):
                return v
    return None


def _extract_dc_observations(raw: Any) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Best-effort extraction of Data Commons observations from datacommons-mcp `get_observations`.
    Returns (observations, source_metadata).
    """
    d = _as_json_dict(raw)
    if d is None:
        return [], None

    src_meta = d.get("source_metadata") if isinstance(d.get("source_metadata"), dict) else None

    # Common shapes:
    # - {"observations":[{"date":"2021","value":...}, ...]}
    # - {"data":[{"date":"2021","value":...}, ...]}
    # - {"observationsByVariable": {...}} (ignore for now)
    obs = d.get("observations")
    if isinstance(obs, list):
        return [o for o in obs if isinstance(o, dict)], src_meta

    data = d.get("data")
    if isinstance(data, list):
        return [o for o in data if isinstance(o, dict)], src_meta

    return [], src_meta


class SdohObservationsTool(StructuredTool):
    """
    Unified observations facade for SDoH indicators.

    Step 2: Data Commons-backed via batched v2 observation API when DC_API_KEY is set
    (avoids hundreds of MCP get_observations calls). Falls back to MCP get_observations
    per place only if DC_API_KEY is missing. CMS/IHME are stubs. Normalizes join keys
    and can join on (place_key, year) when multiple indicators are requested.
    """

    def __init__(self, dc_observations_tool: StructuredTool):
        super().__init__(
            name="get_sdoh_observations",
            description=(
                "Fetch observations for one or more SDoH indicators across sources. "
                "Data Commons is implemented; CMS/IHME are stubs. "
                "Normalizes place_key and year and can join on (place_key, year)."
            ),
            args_schema=GetSDoHObservationsInput,
            func=self._run,
        )
        object.__setattr__(self, "_dc_observations_tool", dc_observations_tool)

    def _call_dc_get_observations(self, variable_dcid: str, place_dcid: str, date: str) -> Any:
        tool = getattr(self, "_dc_observations_tool", None)
        if tool is None:
            raise RuntimeError("Data Commons observations tool not configured.")

        # Keep resilient to schema differences.
        attempts = [
            {"variable_dcid": variable_dcid, "place_dcid": place_dcid, "date": date},
            {"variable": variable_dcid, "place": place_dcid, "date": date},
            {"stat_var": variable_dcid, "place_dcid": place_dcid, "date": date},
            {"stat_var_dcid": variable_dcid, "place_dcid": place_dcid, "date": date},
        ]
        last_err: Optional[Exception] = None
        for kwargs in attempts:
            try:
                return tool.invoke(kwargs)
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(
            f"Failed calling Data Commons get_observations for variable={variable_dcid!r} place={place_dcid!r} date={date!r}: {last_err}"
        )

    def _run(
        self,
        indicators: List[str],
        place: PlaceRequest,
        time: Optional[TimeRequest] = None,
        join: Optional[JoinRequest] = None,
        output: Optional[OutputRequest] = None,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        indicators = [str(x).strip() for x in (indicators or []) if str(x).strip()]
        if not indicators:
            raise ValueError("indicators must be a non-empty list of indicator_id strings.")

        join_cfg = join or JoinRequest()
        out_cfg = output or OutputRequest()

        allowed_sources = [s.lower() for s in (sources or ["datacommons", "cms", "ihme"])]
        warnings: List[str] = []

        # Guardrail: multi-indicator requests must specify both time and place.
        if len(indicators) > 1:
            if time is None or (time.year is None and not time.years):
                raise ValueError("When requesting multiple indicators, `time.year` or `time.years` is required.")
            if not place or (not place.ids and not place.within):
                raise ValueError("When requesting multiple indicators, `place.ids` or `place.within` is required.")

        # Resolve time list
        years: List[Optional[int]] = []
        if time is None or (time.year is None and not time.years):
            years = [None]  # means "latest"
        else:
            if time.year is not None:
                years.append(int(time.year))
            if time.years:
                years.extend([int(y) for y in time.years if y is not None])
            # de-dupe, stable
            seen = set()
            years = [y for y in years if (y not in seen and not seen.add(y))]

        raw_place_ids = [str(pid).strip() for pid in (place.ids or []) if str(pid).strip()]
        user_supplied_place_ids = place.ids is not None and len(raw_place_ids) > 0
        if user_supplied_place_ids:
            place_ids = expand_places_for_parent_and_level(
                level=str(place.level),
                within=None,
                explicit_ids=raw_place_ids,
                warnings=warnings,
            )
            if not place_ids:
                warnings.append("No valid place DCIDs after normalizing `place.ids`; not expanding `within`.")
        else:
            place_ids = expand_places_for_parent_and_level(
                level=str(place.level),
                within=place.within,
                explicit_ids=None,
                warnings=warnings,
            )

        rows: List[Dict[str, Any]] = []
        sources_checked: List[str] = []

        dc_pairs: List[Tuple[str, str]] = []
        for indicator_id in indicators:
            src, native = _parse_indicator_id(indicator_id)

            if src not in allowed_sources:
                warnings.append(f"Skipping indicator {indicator_id!r} because its source {src!r} is not in allowlist.")
                continue

            if src == "cms":
                sources_checked.append("cms")
                warnings.append("CMS observations not implemented yet (stub).")
            elif src == "ihme":
                sources_checked.append("ihme")
                warnings.append("IHME observations not implemented yet (stub).")
            elif src == "datacommons":
                if "datacommons" not in sources_checked:
                    sources_checked.append("datacommons")
                if not native:
                    warnings.append(f"Empty Data Commons native_id for indicator {indicator_id!r}; skipping.")
                    continue
                dc_pairs.append((indicator_id, native))
            else:
                warnings.append(f"Unknown indicator source {src!r} for indicator {indicator_id!r}; skipping.")

        if dc_pairs and place_ids:
            native_to_indicator: Dict[str, str] = {}
            for iid, nat in dc_pairs:
                native_to_indicator[str(nat)] = iid
            variable_dcids = list(dict.fromkeys([str(nat) for _, nat in dc_pairs]))

            if dc_api_key():
                for y in years:
                    dedupe_keys: set = set()
                    batch_rows = fetch_observations_by_entity_batch(
                        place_ids,
                        variable_dcids,
                        year=(None if y is None else int(y)),
                    )
                    if not batch_rows:
                        if y is not None:
                            warnings.append(
                                f"No batched Data Commons observations for year {int(y)} "
                                f"(variables={variable_dcids!r})."
                            )
                        else:
                            warnings.append(f"No batched Data Commons observations for latest (variables={variable_dcids!r}).")

                    for rec in batch_rows:
                        ent = rec.get("entity")
                        var = rec.get("variable")
                        if not ent or not var:
                            continue
                        ind_id = native_to_indicator.get(str(var))
                        if not ind_id:
                            continue
                        native = str(var)
                        place_key = normalize_place_key(str(ent), warnings) or str(ent)
                        oy = _normalize_year(rec.get("date"))
                        if y is not None:
                            if oy is None or int(oy) != int(y):
                                continue
                        dk = (place_key, str(var), str(rec.get("date")), str(rec.get("facetId")))
                        if dk in dedupe_keys:
                            continue
                        dedupe_keys.add(dk)

                        value = rec.get("value")
                        try:
                            value_num = float(value) if value is not None and value != "" else None
                        except Exception:
                            value_num = None

                        metric_source = None
                        if out_cfg.include_metric_source:
                            import_name = rec.get("importName")
                            source_id = rec.get("facetId")
                            provenance_url = rec.get("provenanceUrl")
                            if import_name or provenance_url or (source_id not in (None, "", "unknown")):
                                metric_source = {
                                    "name": import_name or source_id,
                                    "import_name": import_name,
                                    "source_id": source_id,
                                    "measurement_method": rec.get("measurementMethod"),
                                    "observation_period": rec.get("observationPeriod"),
                                    "url": provenance_url,
                                }

                        row: Dict[str, Any] = {
                            "place_key": place_key,
                            "place_name": None,
                            "place_level": place.level,
                            "year": int(y) if y is not None else (int(oy) if oy is not None else None),
                            "indicator_id": ind_id,
                            "value": value_num,
                            "unit": rec.get("unit"),
                            "source": "datacommons",
                            "native_id": native,
                        }
                        if out_cfg.include_repository:
                            row["repository"] = {"name": "Data Commons"}
                        if out_cfg.include_metric_source:
                            row["metric_source"] = metric_source
                        if not out_cfg.include_place_columns:
                            row.pop("place_name", None)
                            row.pop("place_level", None)
                        rows.append(row)
            else:
                warnings.append(
                    "DC_API_KEY is not set; using MCP get_observations once per place per variable (slow for many counties). "
                    "Set DC_API_KEY to enable batched Data Commons v2 fetches."
                )
                for indicator_id, native in dc_pairs:
                    for pid in place_ids:
                        place_key = normalize_place_key(pid, warnings)
                        if not place_key:
                            continue
                        for y in years:
                            date = "latest" if y is None else str(int(y))
                            raw = self._call_dc_get_observations(variable_dcid=native, place_dcid=place_key, date=date)
                            obs_list, src_meta = _extract_dc_observations(raw)

                            metric_source = None
                            if out_cfg.include_metric_source and src_meta:
                                import_name = src_meta.get("import_name")
                                source_id = src_meta.get("source_id")
                                provenance_url = src_meta.get("provenance_url")
                                if import_name or provenance_url or (source_id not in (None, "", "unknown")):
                                    metric_source = {
                                        "name": import_name or source_id,
                                        "import_name": import_name,
                                        "source_id": source_id,
                                        "measurement_method": src_meta.get("measurement_method"),
                                        "observation_period": src_meta.get("observation_period"),
                                        "url": provenance_url,
                                    }

                            if not obs_list:
                                if y is not None:
                                    warnings.append(
                                        f"No Data Commons observations found for {native!r} at {place_key!r} for year {int(y)}."
                                    )
                                else:
                                    warnings.append(
                                        f"No Data Commons observations found for {native!r} at {place_key!r} (latest)."
                                    )
                                continue

                            for o in obs_list:
                                oy = _normalize_year(_coalesce(o, ["year", "date"]))
                                if y is not None and oy is not None and int(oy) != int(y):
                                    continue
                                if y is not None and oy is None:
                                    continue

                                value = _coalesce(o, ["value", "val"])
                                try:
                                    value_num = float(value) if value is not None and value != "" else None
                                except Exception:
                                    value_num = None

                                row = {
                                    "place_key": place_key,
                                    "place_name": None,
                                    "place_level": place.level,
                                    "year": int(y) if y is not None else (int(oy) if oy is not None else None),
                                    "indicator_id": indicator_id,
                                    "value": value_num,
                                    "unit": _coalesce(o, ["unit", "unit_display_name", "unitDisplayName"]),
                                    "source": "datacommons",
                                    "native_id": native,
                                }
                                if out_cfg.include_repository:
                                    row["repository"] = {"name": "Data Commons"}
                                if out_cfg.include_metric_source:
                                    row["metric_source"] = metric_source
                                if not out_cfg.include_place_columns:
                                    row.pop("place_name", None)
                                    row.pop("place_level", None)
                                rows.append(row)
        elif dc_pairs and not place_ids:
            warnings.append(
                "No place DCIDs resolved for Data Commons observations "
                "(provide place.ids, or place.within + level with DC_API_KEY for v2 expansion)."
            )

        # Normalize year presence
        for r in rows:
            if r.get("year") is None:
                # Latest without a year is not joinable; keep but warn.
                warnings.append("Some rows have no `year` (latest observations); joins on (place_key, year) may be skipped.")
                break

        # Join behavior (only meaningful for multi-indicator requests)
        join_status: Dict[str, Any] = {
            "join_attempted": False,
            "join_succeeded": False,
            "join_keys": join_cfg.join_keys,
            "join_type": join_cfg.join_type,
            "warnings": [],
        }

        data_out_rows: List[Dict[str, Any]] = rows
        if len(indicators) > 1 and join_cfg.attempt_join:
            if out_cfg.format == "wide":
                join_status["join_attempted"] = True
                df = pd.DataFrame(rows)
                required_cols = {"place_key", "year", "indicator_id", "value"}
                if not required_cols.issubset(set(df.columns)):
                    join_status["warnings"].append(
                        f"Cannot join: missing required columns {sorted(list(required_cols - set(df.columns)))}."
                    )
                else:
                    dfj = df.dropna(subset=["place_key", "year"])
                    if dfj.empty:
                        join_status["warnings"].append("Cannot join: no rows with both place_key and year.")
                    else:
                        # Pivot indicator values to columns; keep first value deterministically.
                        wide = (
                            dfj.sort_values(["place_key", "year", "indicator_id"])
                            .pivot_table(
                                index=["place_key", "year"],
                                columns="indicator_id",
                                values="value",
                                aggfunc="first",
                            )
                            .reset_index()
                        )
                        # Flatten columns
                        wide.columns = [str(c) for c in wide.columns]
                        join_status["join_succeeded"] = True
                        data_out_rows = wide.to_dict(orient="records")

                        # Warn if inner join dropped coverage vs long
                        joined_pairs = set(zip(wide["place_key"].tolist(), wide["year"].tolist()))
                        all_pairs = set(zip(dfj["place_key"].tolist(), dfj["year"].tolist()))
                        dropped = len(all_pairs - joined_pairs)
                        if dropped > 0:
                            join_status["warnings"].append(f"Join dropped {dropped} (place_key, year) rows due to missing coverage.")
            else:
                # Long format: we don't physically join, but we can still provide guidance.
                join_status["join_attempted"] = False
                join_status["warnings"].append("Output format is long; join not materialized (set output.format='wide' to join).")

        # Schema: best-effort types
        schema_cols: List[Dict[str, Any]] = []
        if data_out_rows:
            sample = data_out_rows[0]
            for k, v in sample.items():
                if isinstance(v, (int, float)) or v is None:
                    typ = "number"
                elif isinstance(v, dict):
                    typ = "object"
                else:
                    typ = "string"
                schema_cols.append({"name": k, "type": typ})

        place_resolution = {
            "requested_count": len(place_ids) if place_ids else 0,
            "resolved_count": len(place_ids) if place_ids else 0,
            "unmatched_count": 0,
            "warnings": [w for w in warnings if "Place-name resolution" in w or "place id" in w],
        }

        return {
            "data": data_out_rows,
            "schema": {"columns": schema_cols},
            "join_status": join_status,
            "place_resolution": place_resolution,
            "sources_checked": list(dict.fromkeys(sources_checked)),
            "warnings": warnings,
        }

