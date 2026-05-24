from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

# Fallback Socrata ids when catalog discovery fails (2025 Local Data release).
CDC_PLACES_DATASETS_FALLBACK: Dict[str, str] = {
    "county": "swc5-untb",
    "place": "eav7-hnsx",
    "city": "eav7-hnsx",
    "zip": "qnzd-25i4",
    "zcta": "qnzd-25i4",
    "tract": "cwsq-ngmh",
}

# Deprecated alias for tests/docs; prefer get_places_datasets().
CDC_PLACES_DATASETS: Dict[str, str] = CDC_PLACES_DATASETS_FALLBACK

_SOCRATA_CATALOG_API = "https://api.us.socrata.com/api/catalog/v1"
_DATASET_REGISTRY_CACHE: Optional[Tuple[float, Dict[str, str], Dict[str, Any]]] = None
_DATASET_REGISTRY_TTL_SEC = 86400
_DEFAULT_RELEASE_YEAR = 2025

MAX_PLACES_LOCATION_IDS = 200

DATA_VALUE_TYPE_IDS: Dict[str, str] = {
    "AgeAdjPrv": "Age-adjusted prevalence",
    "CrdPrv": "Crude prevalence",
}

_VALUE_TYPE_ALIASES: Dict[str, str] = {
    "ageadjprv": "AgeAdjPrv",
    "age_adj_prv": "AgeAdjPrv",
    "age-adjusted": "AgeAdjPrv",
    "age adjusted": "AgeAdjPrv",
    "age-adjusted prevalence": "AgeAdjPrv",
    "age adjusted prevalence": "AgeAdjPrv",
    "adjusted": "AgeAdjPrv",
    "crdprv": "CrdPrv",
    "crudeprev": "CrdPrv",
    "crude prevalence": "CrdPrv",
    "crude": "CrdPrv",
}

_LOCATION_ID_LENGTHS: Dict[str, Set[int]] = {
    "county": {5},
    "state": {2},
    "place": {7},
    "city": {7},
    "zip": {5},
    "zcta": {5},
    "tract": {11},
}

_NATIVE_ID_RE = re.compile(r"^([^/]+)/([^/]+)/([^/]+)$", re.IGNORECASE)
_SOCRATA_BASE = "https://data.cdc.gov/resource"
_IN_CLAUSE_BATCH = 150
_PAGE_SIZE = 5000
_MEASURE_INDEX_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_MEASURE_INDEX_TTL_SEC = 86400


def normalize_places_geo_level(level: str) -> str:
    s = str(level or "").strip().lower()
    if s in ("city", "other"):
        return "place"
    if s == "zcta":
        return "zip"
    return s


def normalize_data_value_type_id(raw: str) -> Optional[str]:
    s = str(raw or "").strip()
    if not s:
        return None
    if s in DATA_VALUE_TYPE_IDS:
        return s
    key = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    if key in _VALUE_TYPE_ALIASES:
        return _VALUE_TYPE_ALIASES[key]
    compact = re.sub(r"[^a-z0-9]", "", s.lower())
    for alias, canonical in _VALUE_TYPE_ALIASES.items():
        if compact == re.sub(r"[^a-z0-9]", "", alias):
            return canonical
    if compact == "ageadjprv":
        return "AgeAdjPrv"
    if compact in ("crdprv", "crudeprev"):
        return "CrdPrv"
    return None


def resolve_measure_id(raw: str) -> Optional[str]:
    """Normalize a PLACES measureid token from an indicator native_id (uppercase)."""
    s = str(raw or "").strip().upper()
    return s if s else None


def parse_native_id(native_id: str) -> Tuple[str, str, str]:
    m = _NATIVE_ID_RE.match(str(native_id or "").strip())
    if not m:
        raise ValueError(
            f"Invalid CDC PLACES native_id {native_id!r}; expected geo_level/MeasureId/DataValueTypeID."
        )
    geo_level = normalize_places_geo_level(m.group(1).strip())
    measure_raw = m.group(2).strip()
    value_type_raw = m.group(3).strip()
    measure_id = resolve_measure_id(measure_raw) or measure_raw.upper()
    value_type_id = normalize_data_value_type_id(value_type_raw)
    if not value_type_id:
        raise ValueError(f"Unknown CDC PLACES DataValueTypeID {value_type_raw!r}.")
    return geo_level, measure_id, value_type_id


def build_indicator_id(geo_level: str, measure_id: str, data_value_type_id: str) -> str:
    geo = normalize_places_geo_level(geo_level)
    return f"cdcplaces:{geo}/{measure_id}/{data_value_type_id}"


def places_release_year() -> int:
    """
    Target PLACES catalog release year for dataset auto-discovery.

    Reads ``CDC_PLACES_RELEASE_YEAR`` from the environment; defaults to 2025.
    """
    raw = os.environ.get("CDC_PLACES_RELEASE_YEAR", "").strip()
    if raw.isdigit():
        return int(raw)
    return _DEFAULT_RELEASE_YEAR


def geo_level_from_catalog_name(name: str) -> Optional[str]:
    """
    Map a data.cdc.gov catalog dataset title to a PLACES geo level key.

    Recognizes County, Place, ZCTA, and Census Tract Local Data titles.
    Returns ``None`` for non-PLACES or GIS-friendly duplicate datasets.
    """
    n = str(name or "").strip().lower()
    if "places" not in n or "local data for better health" not in n:
        return None
    if "gis friendly" in n:
        return None
    if "county data" in n:
        return "county"
    if "census tract data" in n:
        return "tract"
    if "zcta data" in n:
        return "zip"
    if "place data" in n:
        return "place"
    if "state data" in n:
        return "state"
    return None


def release_year_from_catalog_name(name: str) -> Optional[int]:
    """
    Extract a four-digit release year from a PLACES catalog dataset title.

    Handles patterns such as ``2025 release`` and ``County Data 2024 release``.
    """
    n = str(name or "")
    for pat in (
        r"(\d{4})\s*release",
        r"release[,\s]+(\d{4})",
        r",\s*(\d{4})\s*release",
    ):
        m = re.search(pat, n, flags=re.IGNORECASE)
        if m:
            y = int(m.group(1))
            if 2010 <= y <= 2100:
                return y
    return None


def fetch_places_catalog_hits(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Query the Socrata catalog API for PLACES Local Data datasets on data.cdc.gov.

    Returns raw catalog ``results`` entries (each has a ``resource`` object with
    ``id`` and ``name``). Network errors propagate to the caller.
    """
    params = urllib.parse.urlencode(
        {
            "domains": "data.cdc.gov",
            "q": "PLACES Local Data for Better Health",
            "limit": str(int(limit)),
        }
    )
    url = f"{_SOCRATA_CATALOG_API}?{params}"
    req = urllib.request.Request(url, headers=_socrata_headers())
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


def discover_places_datasets(
    release_year: Optional[int] = None,
    force_refresh: bool = False,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Discover PLACES Socrata dataset ids by geography via the data.cdc.gov catalog.

    For each geo level (county, place, zip, tract, and state if published), selects the
    dataset whose title matches ``places_release_year()`` (or the provided
    ``release_year``). If no exact year match exists, uses the newest available year
    for that geography. GIS-friendly duplicate datasets are ignored.

    Returns:
        (datasets, metadata) where ``datasets`` maps geo level → Socrata resource id
        (e.g. ``{"county": "swc5-untb", ...}``), and ``metadata`` includes
        ``source`` (``catalog`` or ``fallback``), ``release_year``, and per-geo
        ``entries`` with catalog names.

    On catalog failure, returns ``CDC_PLACES_DATASETS_FALLBACK`` with
    ``metadata["source"] == "fallback"``.
    """
    global _DATASET_REGISTRY_CACHE

    target_year = int(release_year) if release_year is not None else places_release_year()
    now = time.time()

    if not force_refresh and _DATASET_REGISTRY_CACHE is not None:
        ts, datasets, meta = _DATASET_REGISTRY_CACHE
        if (now - ts) < _DATASET_REGISTRY_TTL_SEC and meta.get("release_year") == target_year:
            return datasets, meta

    candidates: Dict[str, List[Tuple[int, str, str]]] = {}
    try:
        hits = fetch_places_catalog_hits()
    except Exception as exc:
        meta = {
            "source": "fallback",
            "release_year": target_year,
            "error": f"{type(exc).__name__}: {exc}",
            "entries": {},
        }
        datasets = dict(CDC_PLACES_DATASETS_FALLBACK)
        _DATASET_REGISTRY_CACHE = (now, datasets, meta)
        return datasets, meta

    for hit in hits:
        resource = hit.get("resource") if isinstance(hit.get("resource"), dict) else {}
        dataset_id = resource.get("id")
        name = resource.get("name")
        if not dataset_id or not name:
            continue
        geo = geo_level_from_catalog_name(str(name))
        if not geo:
            continue
        year = release_year_from_catalog_name(str(name)) or 0
        candidates.setdefault(geo, []).append((year, str(dataset_id), str(name)))

    datasets: Dict[str, str] = {}
    entries: Dict[str, Dict[str, Any]] = {}
    for geo, items in candidates.items():
        if not items:
            continue
        exact = [x for x in items if x[0] == target_year]
        pool = exact if exact else items
        year, dataset_id, name = max(pool, key=lambda x: x[0])
        datasets[geo] = dataset_id
        entries[geo] = {"dataset_id": dataset_id, "catalog_name": name, "release_year": year}

    # Aliases share the same Socrata table as place / zip parents.
    if "place" in datasets:
        datasets["city"] = datasets["place"]
    if "zip" in datasets:
        datasets["zcta"] = datasets["zip"]

    # Fill gaps from fallback so partial catalog matches still work.
    for geo, dataset_id in CDC_PLACES_DATASETS_FALLBACK.items():
        if geo not in datasets:
            datasets[geo] = dataset_id
            entries[geo] = {
                "dataset_id": dataset_id,
                "catalog_name": None,
                "release_year": target_year,
                "filled_from_fallback": True,
            }

    source = "catalog" if candidates else "fallback"
    if not candidates:
        datasets = dict(CDC_PLACES_DATASETS_FALLBACK)
    meta = {
        "source": source,
        "release_year": target_year,
        "entries": entries,
    }
    _DATASET_REGISTRY_CACHE = (now, datasets, meta)
    return datasets, meta


def get_places_datasets(force_refresh: bool = False) -> Dict[str, str]:
    """
    Return the geo level → Socrata dataset id map used for search and observations.

    Uses :func:`discover_places_datasets` (cached). Call with ``force_refresh=True``
    to bypass the cache after CDC publishes a new release.
    """
    datasets, _ = discover_places_datasets(force_refresh=force_refresh)
    return datasets


def places_dataset_registry_metadata() -> Dict[str, Any]:
    """
    Return metadata from the last dataset discovery (release year, catalog names, source).

    Triggers discovery if the cache is cold.
    """
    _, meta = discover_places_datasets()
    return dict(meta)


def dataset_id_for_geo_level(geo_level: str) -> Optional[str]:
    """
    Resolve the Socrata resource id for a PLACES geography level.

    Uses auto-discovered ids from :func:`get_places_datasets`. Returns ``None`` when
    the geo level is unknown or has no configured table (e.g. state if CDC does not
    publish one).
    """
    geo = normalize_places_geo_level(geo_level)
    return get_places_datasets().get(geo)


def _row_get(row: Dict[str, Any], *keys: str) -> Any:
    lower_map = {str(k).lower(): k for k in row.keys()}
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
        lk = k.lower()
        if lk in lower_map:
            v = row.get(lower_map[lk])
            if v not in (None, ""):
                return v
    return None


def place_key_from_location_id(location_id: str, geo_level: str) -> Optional[str]:
    code = re.sub(r"\D", "", str(location_id or "").strip())
    if not code:
        return None
    lvl = normalize_places_geo_level(geo_level)
    if lvl == "county" and len(code) == 5:
        return f"geoId/{code}"
    if lvl == "state" and len(code) == 2:
        return f"geoId/{code}"
    if lvl == "tract" and len(code) == 11:
        return f"geoId/{code}"
    if lvl in ("zip", "zcta") and len(code) == 5:
        return f"zip/{code}"
    if lvl in ("city", "place") and len(code) == 7:
        return f"geoId/{code}"
    return None


def extract_location_ids(
    place_ids: List[str],
    geo_level: str,
    warnings: Optional[List[str]] = None,
) -> List[str]:
    """Map place.ids / expanded DCIDs to PLACES locationid strings for SoQL."""
    geo = normalize_places_geo_level(geo_level)
    allowed = _LOCATION_ID_LENGTHS.get(geo, set())
    out: Set[str] = set()
    for pid in place_ids or []:
        s = str(pid).strip()
        if not s:
            continue
        if geo == "county" and s.lower().startswith("zip/"):
            continue
        if geo in ("zip", "zcta") and s.lower().startswith("zip/"):
            tail = s.split("/", 1)[-1].strip()
            if tail.isdigit() and len(tail) == 5:
                out.add(tail)
            continue
        code = re.sub(r"\D", "", s)
        if not code:
            continue
        if allowed:
            if len(code) in allowed:
                out.add(code)
            elif geo == "county" and len(code) == 5:
                out.add(code)
        else:
            out.add(code)
    if warnings is not None and not out and place_ids:
        warnings.append(
            f"CDC PLACES: no locationid values extracted for geo_level={geo!r} from "
            f"{len(place_ids)} place id(s); check place.level matches indicator geo."
        )
    return sorted(out)


def _socrata_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "SDoH-Public-Data-Assistant/1.0"}
    token = os.environ.get("CDC_PLACES_APP_TOKEN", "").strip()
    if token:
        headers["X-App-Token"] = token
    return headers


def _socrata_get_json(path_and_query: str) -> Any:
    url = f"{_SOCRATA_BASE}/{path_and_query}"
    req = urllib.request.Request(url, headers=_socrata_headers())
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_measure_index(geo_level: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Distinct measures + value types from Socrata ($group). Cached per dataset id.
    """
    geo = normalize_places_geo_level(geo_level)
    dataset_id = dataset_id_for_geo_level(geo)
    if not dataset_id:
        return []

    now = time.time()
    cached = _MEASURE_INDEX_CACHE.get(dataset_id)
    if not force_refresh and cached and (now - cached[0]) < _MEASURE_INDEX_TTL_SEC:
        return cached[1]

    params = urllib.parse.urlencode(
        {
            "$select": "measureid,measure,category,datavaluetypeid,data_value_type",
            "$group": "measureid,measure,category,datavaluetypeid,data_value_type",
            "$limit": "5000",
        }
    )
    payload = _socrata_get_json(f"{dataset_id}.json?{params}")
    rows: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        for r in payload:
            if isinstance(r, dict) and r.get("measureid"):
                rows.append(
                    {
                        "measure_id": str(r["measureid"]).strip().upper(),
                        "measure": r.get("measure"),
                        "category": r.get("category"),
                        "data_value_type_id": r.get("datavaluetypeid"),
                        "data_value_type_label": r.get("data_value_type"),
                    }
                )
    _MEASURE_INDEX_CACHE[dataset_id] = (now, rows)
    return rows


def fetch_places_rows(
    dataset_id: str,
    measure_id: str,
    data_value_type_id: str,
    location_ids: List[str],
    year: Optional[int] = None,
    offset: int = 0,
    limit: int = _PAGE_SIZE,
) -> List[Dict[str, Any]]:
    if not location_ids:
        return []
    locs = [re.sub(r"\D", "", str(x)) for x in location_ids if str(x).strip()]
    locs = [x for x in locs if x]
    if not locs:
        return []

    loc_clause = ",".join(f"'{x}'" for x in locs)
    where_parts = [
        f"measureid = '{measure_id}'",
        f"datavaluetypeid = '{data_value_type_id}'",
        f"locationid in({loc_clause})",
    ]
    if year is not None:
        where_parts.append(f"year = '{int(year)}'")
    params = urllib.parse.urlencode(
        {
            "$where": " AND ".join(where_parts),
            "$limit": str(int(limit)),
            "$offset": str(int(offset)),
        }
    )
    payload = _socrata_get_json(f"{dataset_id}.json?{params}")
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def fetch_places_observations_batched(
    geo_level: str,
    measure_id: str,
    data_value_type_id: str,
    location_ids: List[str],
    year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    dataset_id = dataset_id_for_geo_level(geo_level)
    if not dataset_id:
        return []
    out: List[Dict[str, Any]] = []
    locs = [re.sub(r"\D", "", str(x)) for x in location_ids if str(x).strip()]
    locs = [x for x in locs if x]
    for i in range(0, len(locs), _IN_CLAUSE_BATCH):
        batch = locs[i : i + _IN_CLAUSE_BATCH]
        offset = 0
        while True:
            page = fetch_places_rows(
                dataset_id,
                measure_id,
                data_value_type_id,
                batch,
                year=year,
                offset=offset,
                limit=_PAGE_SIZE,
            )
            if not page:
                break
            out.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
    return out


def metric_source_from_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    datasource = _row_get(row, "datasource")
    category = _row_get(row, "category")
    short_q = _row_get(row, "short_question_text")
    value_type_label = _row_get(row, "data_value_type")
    population_note = _row_get(row, "totalpop18plus")
    parts = []
    if datasource:
        parts.append(str(datasource))
    if category:
        parts.append(str(category))
    if value_type_label:
        parts.append(str(value_type_label))
    if short_q:
        parts.append(str(short_q))
    if not parts:
        return None
    out: Dict[str, Any] = {"name": " — ".join(parts)}
    if datasource:
        out["datasource"] = datasource
    if category:
        out["category"] = category
    if value_type_label:
        out["data_value_type"] = value_type_label
    if short_q:
        out["short_question_text"] = short_q
    if population_note is not None:
        out["population_denominator_note"] = "Adults 18+ (see totalpop18plus in source row)"
    return out


def _query_wants_age_adjusted(query: str) -> bool:
    q = str(query or "").lower()
    return any(
        t in q
        for t in (
            "age-adjusted",
            "age adjusted",
            "ageadj",
            "age adj",
            "adjusted rate",
            "adjusted prevalence",
        )
    )


def _query_wants_crude(query: str) -> bool:
    q = str(query or "").lower()
    return "crude" in q and not _query_wants_age_adjusted(query)


def _infer_geo_level(query: str, place_scope_level: Optional[str]) -> str:
    if place_scope_level:
        return normalize_places_geo_level(place_scope_level)
    q = str(query or "").lower()
    for lvl in ("county", "tract", "zcta", "zip", "place", "state"):
        if lvl in q:
            return normalize_places_geo_level(lvl)
    return "county"


def _query_terms(query: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9]+", (query or "").lower()) if len(t) >= 3]


def _score_measure_row(row: Dict[str, Any], terms: List[str], query: str) -> int:
    hay = " ".join(
        [
            str(row.get("measure_id") or ""),
            str(row.get("measure") or ""),
            str(row.get("category") or ""),
        ]
    ).lower()
    score = 0
    q = str(query or "").lower()
    measure_name = str(row.get("measure") or "").lower()
    if q and measure_name and measure_name in q:
        score += 40
    for t in terms:
        if not t:
            continue
        if len(t) >= 4 and t in hay:
            score += 5
        elif len(t) == 3 and re.search(rf"\b{re.escape(t)}\b", hay):
            score += 3
    if "health-related social needs" in hay or "hrsn" in q:
        if any(t in terms for t in ("lonely", "loneliness", "food", "hunger", "housing", "transport", "utility", "snap")):
            if any(t in hay for t in ("lonel", "food", "hous", "transport", "utility", "stamp", "insec")):
                score += 6
    return score


def _candidate_from_measure_row(
    row: Dict[str, Any],
    geo_level: str,
    value_type_id: str,
) -> Dict[str, Any]:
    measure_id = str(row["measure_id"])
    vt = value_type_id or row.get("data_value_type_id")
    if not vt:
        return {}
    vt = str(vt)
    native_id = f"{geo_level}/{measure_id}/{vt}"
    label = DATA_VALUE_TYPE_IDS.get(vt) or row.get("data_value_type_label") or vt
    return {
        "indicator_id": build_indicator_id(geo_level, measure_id, vt),
        "source": "cdcplaces",
        "native_id": native_id,
        "name": row.get("measure") or measure_id,
        "type": "CDCPlacesMeasure",
        "description": (
            f"{row.get('measure')} ({label}; datavaluetypeid={vt}). "
            f"Population: adults (BRFSS model-based)."
        ),
        "repository": {"name": "CDC PLACES"},
        "metric_source": {
            "name": "BRFSS (CDC PLACES model-based)",
            "datasource": "BRFSS",
            "category": row.get("category"),
            "data_value_type": label,
        },
        "catalog_metadata": {
            "geo_level": geo_level,
            "measure_id": measure_id,
            "data_value_type_id": vt,
            "data_value_type_label": label,
            "discovery": "socrata_measure_index",
        },
    }


def search_catalog(
    query: str,
    max_results: int = 20,
    place_scope_level: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search CDC PLACES measures via cached Socrata distinct-measure index (4b).
    """
    terms = _query_terms(query)
    geo_level = _infer_geo_level(query, place_scope_level)

    if geo_level == "state":
        return []

    if geo_level not in get_places_datasets():
        return []

    if not terms:
        return []

    try:
        index = fetch_measure_index(geo_level)
    except Exception:
        return []

    prefer_age_adj = _query_wants_age_adjusted(query)
    prefer_crude = _query_wants_crude(query)

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for row in index:
        s = _score_measure_row(row, terms, query=query)
        if s <= 0:
            continue
        vt = row.get("data_value_type_id")
        if not vt:
            continue
        bonus = 0
        if prefer_age_adj and vt == "AgeAdjPrv":
            bonus = 3
        elif prefer_crude and vt == "CrdPrv":
            bonus = 3
        scored.append((s + bonus, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    out: List[Dict[str, Any]] = []
    for _, row in scored:
        vt = str(row.get("data_value_type_id") or "")
        item = _candidate_from_measure_row(row, geo_level, vt)
        if item:
            reg = places_dataset_registry_metadata()
            if reg.get("entries", {}).get(geo_level):
                item.setdefault("catalog_metadata", {})
                item["catalog_metadata"]["places_dataset"] = reg["entries"][geo_level]
            out.append(item)
        if len(out) >= max_results:
            break
    return out
