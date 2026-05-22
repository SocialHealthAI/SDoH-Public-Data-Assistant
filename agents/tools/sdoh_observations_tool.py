from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

import pandas as pd
import urllib.parse
import urllib.request
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from tools.cdc_places_helpers import (
    MAX_PLACES_LOCATION_IDS,
    dataset_id_for_geo_level,
    extract_location_ids,
    fetch_places_observations_batched,
    metric_source_from_row,
    normalize_places_geo_level,
    parse_native_id,
    place_key_from_location_id,
)
from tools.dc_place_expand import expand_places_for_parent_and_level, normalize_place_key
from tools.dc_v2_helpers import dc_api_key, fetch_observations_by_entity_batch, fetch_property_values_map


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


_GEOID_RE = re.compile(r"^geoId/(\d+)$", re.IGNORECASE)


def _geoid_code(place_key: str) -> Optional[str]:
    m = _GEOID_RE.match(str(place_key).strip())
    return m.group(1) if m else None


_ZIP_PLACE_RE = re.compile(r"^zip/(\d{5})$", re.IGNORECASE)


def _cms_zip_tail_from_place_id(place_id: str) -> Optional[str]:
    """
    Extract a 5-digit ZIP code string from a place id for CMS row matching.
    Accepts zip/45202, bare 45202, or geoId/45202 (last form is ambiguous but used when
    callers normalize numeric ZCTA-like ids to geoId/*).
    """
    s = str(place_id).strip()
    if not s:
        return None
    m = _ZIP_PLACE_RE.match(s)
    if m:
        return m.group(1)
    if s.isdigit() and len(s) == 5:
        return s
    if "/" in s:
        tail = s.split("/", 1)[1].strip()
        if tail.isdigit() and len(tail) == 5:
            return tail
    return None


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", "")
        if s == "":
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def _norm_key_name(k: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(k).strip().lower()).strip("_")


_CMS_DATA_API = "https://data.cms.gov/data-api/v1"


def _cms_data_url(dataset_uuid: str) -> str:
    return f"{_CMS_DATA_API}/dataset/{dataset_uuid}/data"


def _cms_fetch_rows(dataset_uuid: str, offset: int = 0, size: int = 500) -> List[Dict[str, Any]]:
    params = {"offset": int(offset), "size": int(size)}
    url = _cms_data_url(dataset_uuid) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "Data-Analytic-Assistant/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def _cms_pick_fields(sample_row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Pick (year_field, state_field, county_field, value_field) from a sample row.
    Minimal v1: best-effort, no guessing beyond simple name heuristics.
    """
    keys = list(sample_row.keys())
    nkeys = {_norm_key_name(k): k for k in keys}

    # Year: strict 4-digit year only (handled later); here we pick a likely key name.
    for cand in ("year", "yr", "reporting_year", "measure_year", "calendar_year"):
        if cand in nkeys:
            year_field = nkeys[cand]
            break
    else:
        year_field = None

    # Geography: prefer explicit fips-like fields.
    state_field = None
    for cand in (
        "state_fips",
        "statefips",
        "state_code",
        "state_name",
        "state_abbr",
        "state_abbreviation",
        "state_id",
        "state",
    ):
        if cand in nkeys:
            state_field = nkeys[cand]
            break

    county_field = None
    for cand in (
        "prscrbr_geo_cd",
        "county_fips",
        "countyfips",
        "county_code",
        "county_name",
        "fips",
        "county_id",
        "county",
    ):
        if cand in nkeys:
            county_field = nkeys[cand]
            break

    # Value: choose a numeric-looking field with a value-ish name, else first numeric field.
    value_field = None
    preferred = (
        "value",
        "measure",
        "rate",
        "count",
        "number",
        "pct",
        "percent",
        "percentage",
        "num",
        "total",
    )
    numeric_fields: List[str] = []
    for k in keys:
        v = sample_row.get(k)
        if _safe_float(v) is not None:
            numeric_fields.append(k)
    for pref in preferred:
        for nk, orig in nkeys.items():
            if pref in nk and orig in numeric_fields:
                value_field = orig
                break
        if value_field:
            break
    if value_field is None and numeric_fields:
        value_field = numeric_fields[0]

    return year_field, state_field, county_field, value_field


def _cms_place_key_from_row(
    row: Dict[str, Any],
    place_level: str,
    state_field: Optional[str],
    county_field: Optional[str],
    *,
    county_name_to_geoid: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """
    Derive join place_key for CMS rows: geoId/<fips> for state/county, zip/<5digits> for ZIP
    (e.g. Medicare Part D Prscrbr_Geo_Lvl == ZIP). Returns None when not mappable.
    """
    lvl = str(place_level).strip().lower()

    # CMS "by geography" layout (e.g. Medicare Part D opioid rates): Prscrbr_Geo_Lvl + Prscrbr_Geo_Cd.
    # State rows use 2-digit state FIPS in Prscrbr_Geo_Cd; county rows use 5-digit county FIPS.
    # This must run before legacy STATE_ID / COUNTY_NAME heuristics so state-level maps work.
    geo_lvl = _coalesce(row, ["Prscrbr_Geo_Lvl", "prscrbr_geo_lvl"])
    geo_cd_raw = _coalesce(row, ["Prscrbr_Geo_Cd", "prscrbr_geo_cd"])
    if geo_lvl is not None and geo_cd_raw is not None:
        geo_cd = str(geo_cd_raw).strip()
        gl = str(geo_lvl).strip()
        if geo_cd.isdigit():
            if lvl == "state" and gl == "State" and len(geo_cd) <= 2:
                return f"geoId/{geo_cd.zfill(2)}"
            if lvl == "county" and gl == "County" and len(geo_cd) == 5:
                return f"geoId/{geo_cd}"
            # Part D uses Prscrbr_Geo_Lvl == "ZIP" (not "Zip Code") with 5-digit USPS ZIP in Prscrbr_Geo_Cd.
            if lvl == "zip" and gl.upper() == "ZIP" and len(geo_cd) == 5:
                return f"zip/{geo_cd}"

    def _state_fips(v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if s.isdigit():
            return s.zfill(2)
        # common: state abbreviation (FL, NY, etc.) - we cannot deterministically map without a table.
        return None

    def _county_fips(v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if s.isdigit():
            # Some datasets store county fips as 5-digit, some as 3-digit.
            if len(s) == 5:
                return s
            if len(s) == 3:
                return s
        return None

    sf = _state_fips(row.get(state_field)) if state_field else None
    cf = _county_fips(row.get(county_field)) if county_field else None

    if lvl == "state":
        if sf:
            return f"geoId/{sf}"
        return None

    if lvl == "county":
        # Prefer 5-digit county fips if present.
        if cf and len(cf) == 5:
            return f"geoId/{cf}"
        # If county is 3-digit and state is known, combine.
        if sf and cf and len(cf) == 3:
            return f"geoId/{sf}{cf}"
        # Fallback: if we have a deterministic name mapping from the requested place set, use it.
        if county_name_to_geoid and county_field:
            cn = row.get(county_field)
            if cn is not None:
                k = str(cn).strip().upper()
                return county_name_to_geoid.get(k)
        return None

    if lvl == "zip":
        return None

    # Minimal v1 doesn't attempt CBSA/HRR without explicit fields/rules.
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

    Data Commons: batched v2 observation API when DC_API_KEY is set (falls back to MCP
    get_observations per place if not). CMS: data-api/v1 dataset fetch with deterministic
    place_key/year normalization for supported schemas (see implementation). CDC PLACES:
    Socrata fetch for cdcplaces:<geo>/<MeasureId>/<DataValueTypeID> (county/place/zip/tract).
    Join keys are (place_key, year); wide output joins multiple indicators.
    """

    def __init__(self, dc_observations_tool: StructuredTool):
        super().__init__(
            name="get_sdoh_observations",
            description=(
                "Fetch observations for one or more SDoH indicators across sources. "
                "Data Commons is fully implemented (batched v2 when DC_API_KEY set). "
                "CMS is implemented for cms:<dataset_uuid> indicators via data.cms.gov "
                "data-api (county/state geo mapping varies by dataset schema). "
                "CDC PLACES is implemented for cdcplaces:<geo_level>/<MeasureId>/<DataValueTypeID> "
                "(county/place/zip/tract; datavaluetypeid AgeAdjPrv or CrdPrv; supports place.within via DC expansion). "
                "Normalizes place_key and year; can join on (place_key, year) in wide format."
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

        allowed_sources = [s.lower() for s in (sources or ["datacommons", "cms", "cdcplaces"])]
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
        cms_indicators: List[Tuple[str, str]] = []
        cdcplaces_indicators: List[Tuple[str, str]] = []
        for indicator_id in indicators:
            src, native = _parse_indicator_id(indicator_id)

            if src not in allowed_sources:
                warnings.append(f"Skipping indicator {indicator_id!r} because its source {src!r} is not in allowlist.")
                continue

            if src == "cms":
                if "cms" not in sources_checked:
                    sources_checked.append("cms")
                if not native:
                    warnings.append(f"Empty CMS native_id for indicator {indicator_id!r}; skipping.")
                    continue
                cms_indicators.append((indicator_id, native))
            elif src == "cdcplaces":
                if "cdcplaces" not in sources_checked:
                    sources_checked.append("cdcplaces")
                if not native:
                    warnings.append(f"Empty CDC PLACES native_id for indicator {indicator_id!r}; skipping.")
                    continue
                cdcplaces_indicators.append((indicator_id, native))
            elif src == "datacommons":
                if "datacommons" not in sources_checked:
                    sources_checked.append("datacommons")
                if not native:
                    warnings.append(f"Empty Data Commons native_id for indicator {indicator_id!r}; skipping.")
                    continue
                dc_pairs.append((indicator_id, native))
            else:
                warnings.append(f"Unknown indicator source {src!r} for indicator {indicator_id!r}; skipping.")

        # CMS observations (minimal v1)
        if cms_indicators:
            lvl_place = str(place.level).lower()
            # Optional filters: state/county use geoId/* tails; ZIP uses zip/<5> or zip digits from ids.
            requested_geoid_codes: set = set()
            requested_zip_codes: set = set()
            for pid in place_ids or []:
                if lvl_place == "zip":
                    zt = _cms_zip_tail_from_place_id(pid)
                    if zt:
                        requested_zip_codes.add(zt)
                else:
                    code = _geoid_code(pid)
                    if code:
                        requested_geoid_codes.add(code)

            # CMS data-api rows are not DCIDs; mapping supports state, county, and ZIP (Part D-style Prscrbr_*).
            if lvl_place not in ("state", "county", "zip"):
                warnings.append(
                    f"CMS observations v1 only supports place.level in {{'state','county','zip'}}. "
                    f"Requested level={place.level!r}."
                )
            elif lvl_place == "zip" and not requested_zip_codes:
                warnings.append(
                    "CMS ZIP-level fetch requires at least one parseable 5-digit ZIP in `place.ids` "
                    "(e.g. 45202, zip/45202, or geoId/45202). Unbounded ZIP scans are not supported."
                )
            else:
                county_name_to_geoid: Optional[Dict[str, str]] = None
                # If DC_API_KEY is available and we have an explicit county set, build a deterministic
                # mapping from county name -> geoId/<fips> using Data Commons place names.
                if lvl_place == "zip" and place_ids:
                    for pid in place_ids:
                        ps = str(pid).strip().lower()
                        if ps.startswith("geoid/") and len(ps.split("/", 1)[-1]) == 5:
                            warnings.append(
                                "ZIP requests: Data Commons ZCTA DCIDs are typically zip/#####; "
                                "geoId/##### was accepted for CMS ZIP matching only—align map data keys with GeoJSON DCIDs."
                            )
                            break

                if str(place.level).lower() == "county" and place_ids and dc_api_key():
                    name_map = fetch_property_values_map(place_ids, "name")
                    if name_map:
                        m: Dict[str, str] = {}
                        for dcid, names in name_map.items():
                            if not names:
                                continue
                            # Prefer the first name; normalize to uppercase and strip common suffix.
                            nm = str(names[0]).strip()
                            nm = re.sub(r"\s+County\s*$", "", nm, flags=re.IGNORECASE).strip().upper()
                            if nm and dcid and dcid.startswith("geoId/"):
                                m[nm] = dcid
                        if m:
                            county_name_to_geoid = m

                for indicator_id, dataset_uuid in cms_indicators:
                    # Fetch a small window to infer fields; then stream more rows as needed.
                    try:
                        sample = _cms_fetch_rows(dataset_uuid, offset=0, size=5)
                    except Exception as e:
                        warnings.append(f"CMS fetch failed for {dataset_uuid}: {type(e).__name__}: {e}")
                        continue
                    if not sample:
                        warnings.append(f"CMS dataset {dataset_uuid} returned no rows.")
                        continue

                    year_field, state_field, county_field, value_field = _cms_pick_fields(sample[0])
                    if value_field is None:
                        warnings.append(f"CMS dataset {dataset_uuid} has no numeric-like fields to use as value.")
                        continue
                    if year_field is None:
                        warnings.append(
                            f"CMS dataset {dataset_uuid} does not expose an annual year field; "
                            f"cannot normalize to (place_key, year) without guessing."
                        )
                        continue
                    if state_field is None and county_field is None:
                        warnings.append(
                            f"CMS dataset {dataset_uuid} does not expose recognizable state/county fields; "
                            f"cannot derive place_key deterministically."
                        )
                        continue

                    # Pull rows in pages. ZIP rows in large CMS files often start after many state/county rows.
                    offset = 0
                    page_size = 2000
                    max_pages = 10
                    if lvl_place == "zip":
                        max_pages = 250  # up to 500k rows scanned for sparse ZIP extraction
                    zip_targets_hit: set = set()

                    for _ in range(max_pages):
                        try:
                            page = _cms_fetch_rows(dataset_uuid, offset=offset, size=page_size)
                        except Exception as e:
                            warnings.append(f"CMS fetch failed for {dataset_uuid} at offset {offset}: {type(e).__name__}: {e}")
                            break
                        if not page:
                            break

                        for rec in page:
                            y = _normalize_year(rec.get(year_field))
                            if y is None:
                                continue
                            if years and years != [None]:
                                # If caller provided explicit years, filter strictly.
                                if y not in [yy for yy in years if yy is not None]:
                                    continue

                            pk = _cms_place_key_from_row(
                                rec,
                                place_level=str(place.level),
                                state_field=state_field,
                                county_field=county_field,
                                county_name_to_geoid=county_name_to_geoid,
                            )
                            if not pk:
                                continue

                            if requested_zip_codes:
                                if not pk.startswith("zip/"):
                                    continue
                                ztail = pk.split("/", 1)[1]
                                if ztail not in requested_zip_codes:
                                    continue
                            elif requested_geoid_codes:
                                code = _geoid_code(pk)
                                if code and code not in requested_geoid_codes:
                                    continue

                            v = _safe_float(rec.get(value_field))
                            unit = None
                            if isinstance(value_field, str):
                                nk = _norm_key_name(value_field)
                                if "percent" in nk or nk.endswith("_pct") or nk.startswith("pct_"):
                                    unit = "%"

                            row: Dict[str, Any] = {
                                "place_key": pk,
                                "place_name": None,
                                "place_level": place.level,
                                "year": int(y),
                                "indicator_id": indicator_id,
                                "value": v,
                                "unit": unit,
                                "source": "cms",
                                "native_id": dataset_uuid,
                            }
                            if out_cfg.include_repository:
                                row["repository"] = {"name": "CMS"}
                            if out_cfg.include_metric_source:
                                row["metric_source"] = None
                            if not out_cfg.include_place_columns:
                                row.pop("place_name", None)
                                row.pop("place_level", None)
                            rows.append(row)
                            if requested_zip_codes and pk.startswith("zip/"):
                                zip_targets_hit.add(pk.split("/", 1)[1])

                        offset += page_size
                        if requested_zip_codes and requested_zip_codes.issubset(zip_targets_hit):
                            break

                    if lvl_place == "zip" and requested_zip_codes and not requested_zip_codes.issubset(zip_targets_hit):
                        missing = sorted(requested_zip_codes - zip_targets_hit)
                        warnings.append(
                            f"CMS ZIP scan did not find all requested ZIPs (missing up to {len(missing)}): "
                            f"{missing[:10]}{'...' if len(missing) > 10 else ''}. "
                            f"Try a larger release year or verify ZIPs exist in the dataset."
                        )

        if cdcplaces_indicators:
            if not place_ids and not place.within:
                warnings.append(
                    "CDC PLACES requires `place.ids` and/or `place.within` (with DC_API_KEY for parent expansion)."
                )
            elif "cdcplaces_year_column" not in warnings:
                warnings.append(
                    "cdcplaces_year_column: PLACES `year` is the BRFSS survey year in the dataset "
                    "(not the PLACES release title year)."
                )

            for indicator_id, native in cdcplaces_indicators:
                try:
                    geo_level, measure_id, value_type_id = parse_native_id(native)
                except ValueError as e:
                    warnings.append(str(e))
                    continue

                if geo_level == "state":
                    warnings.append(
                        "CDC PLACES 2025 Open Data has no state-level table on data.cdc.gov "
                        "(use county/place/ZCTA indicators, or Data Commons for state-level estimates)."
                    )
                    continue

                if not dataset_id_for_geo_level(geo_level):
                    warnings.append(
                        f"CDC PLACES geo_level={geo_level!r} is not configured (no Socrata dataset id)."
                    )
                    continue

                req_level = normalize_places_geo_level(str(place.level))
                ind_level = normalize_places_geo_level(geo_level)
                if req_level != ind_level:
                    warnings.append(
                        f"place.level={place.level!r} does not match indicator geo_level={geo_level!r} "
                        f"for {indicator_id!r}; place ids may not align with PLACES locationid values."
                    )

                location_id_list = extract_location_ids(place_ids or [], geo_level, warnings)
                if not location_id_list:
                    continue

                if len(location_id_list) > MAX_PLACES_LOCATION_IDS:
                    warnings.append(
                        f"CDC PLACES: truncating {len(location_id_list)} locations to "
                        f"{MAX_PLACES_LOCATION_IDS} for SoQL IN clause limits."
                    )
                    location_id_list = location_id_list[:MAX_PLACES_LOCATION_IDS]

                requested_loc = set(location_id_list)

                for y in years:
                    try:
                        raw_rows = fetch_places_observations_batched(
                            geo_level=geo_level,
                            measure_id=measure_id,
                            data_value_type_id=value_type_id,
                            location_ids=location_id_list,
                            year=(None if y is None else int(y)),
                        )
                    except Exception as e:
                        warnings.append(
                            f"CDC PLACES fetch failed for {indicator_id!r}: {type(e).__name__}: {e}"
                        )
                        continue

                    if not raw_rows and value_type_id == "AgeAdjPrv":
                        warnings.append(
                            f"No age-adjusted (datavaluetypeid=AgeAdjPrv) rows for {measure_id!r}; "
                            f"PLACES label is 'Age-adjusted prevalence'."
                        )

                    for rec in raw_rows:
                        loc = rec.get("locationid") or rec.get("LocationID")
                        if loc is None:
                            continue
                        loc_s = re.sub(r"\D", "", str(loc))
                        if loc_s not in requested_loc:
                            continue
                        pk = place_key_from_location_id(str(loc), geo_level)
                        if not pk:
                            continue

                        year_raw = rec.get("year") or rec.get("Year")
                        oy = _normalize_year(year_raw)
                        if y is not None and oy is not None and int(oy) != int(y):
                            continue
                        if y is not None and oy is None:
                            continue

                        val_raw = rec.get("data_value") or rec.get("DataValue")
                        v = _safe_float(val_raw)
                        unit = rec.get("data_value_unit") or rec.get("DataValueUnit")
                        if not unit and "prevalence" in str(
                            rec.get("data_value_type") or rec.get("DataValueType") or ""
                        ).lower():
                            unit = "%"

                        row = {
                            "place_key": pk,
                            "place_name": rec.get("locationname") or rec.get("LocationName"),
                            "place_level": place.level,
                            "year": int(y) if y is not None else (int(oy) if oy is not None else None),
                            "indicator_id": indicator_id,
                            "value": v,
                            "unit": unit,
                            "source": "cdcplaces",
                            "native_id": native,
                        }
                        if out_cfg.include_repository:
                            row["repository"] = {"name": "CDC PLACES"}
                        if out_cfg.include_metric_source:
                            row["metric_source"] = metric_source_from_row(rec)
                        if not out_cfg.include_place_columns:
                            row.pop("place_name", None)
                            row.pop("place_level", None)
                        rows.append(row)

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
                        place_key = normalize_place_key(str(ent), warnings, level=str(place.level)) or str(ent)
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
                        place_key = normalize_place_key(pid, warnings, level=str(place.level))
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

