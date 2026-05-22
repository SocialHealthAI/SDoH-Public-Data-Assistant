"""
Data Commons place containment via REST API v2.

The legacy Python v1 call `datacommons.get_places_in` hits deprecated endpoints (HTTP 410).
Place expansion uses `datacommons-client` (v2): `node.fetch_place_children` and optionally
`node.fetch_place_descendants` when direct children are empty (e.g. cities under a US county).

Requires `DC_API_KEY` (or `DATACOMMONS_API_KEY`) in the environment for v2 calls.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

_US_STATE_TO_FIPS: Dict[str, str] = {
    "alabama": "01",
    "alaska": "02",
    "arizona": "04",
    "arkansas": "05",
    "california": "06",
    "colorado": "08",
    "connecticut": "09",
    "delaware": "10",
    "district of columbia": "11",
    "florida": "12",
    "georgia": "13",
    "hawaii": "15",
    "idaho": "16",
    "illinois": "17",
    "indiana": "18",
    "iowa": "19",
    "kansas": "20",
    "kentucky": "21",
    "louisiana": "22",
    "maine": "23",
    "maryland": "24",
    "massachusetts": "25",
    "michigan": "26",
    "minnesota": "27",
    "mississippi": "28",
    "missouri": "29",
    "montana": "30",
    "nebraska": "31",
    "nevada": "32",
    "new hampshire": "33",
    "new jersey": "34",
    "new mexico": "35",
    "new york": "36",
    "north carolina": "37",
    "north dakota": "38",
    "ohio": "39",
    "oklahoma": "40",
    "oregon": "41",
    "pennsylvania": "42",
    "rhode island": "44",
    "south carolina": "45",
    "south dakota": "46",
    "tennessee": "47",
    "texas": "48",
    "utah": "49",
    "vermont": "50",
    "virginia": "51",
    "washington": "53",
    "west virginia": "54",
    "wisconsin": "55",
    "wyoming": "56",
}

_US_ABBR_TO_FIPS: Dict[str, str] = {
    "al": "01",
    "ak": "02",
    "az": "04",
    "ar": "05",
    "ca": "06",
    "co": "08",
    "ct": "09",
    "de": "10",
    "dc": "11",
    "fl": "12",
    "ga": "13",
    "hi": "15",
    "id": "16",
    "il": "17",
    "in": "18",
    "ia": "19",
    "ks": "20",
    "ky": "21",
    "la": "22",
    "me": "23",
    "md": "24",
    "ma": "25",
    "mi": "26",
    "mn": "27",
    "ms": "28",
    "mo": "29",
    "mt": "30",
    "ne": "31",
    "nv": "32",
    "nh": "33",
    "nj": "34",
    "nm": "35",
    "ny": "36",
    "nc": "37",
    "nd": "38",
    "oh": "39",
    "ok": "40",
    "or": "41",
    "pa": "42",
    "ri": "44",
    "sc": "45",
    "sd": "46",
    "tn": "47",
    "tx": "48",
    "ut": "49",
    "vt": "50",
    "va": "51",
    "wa": "53",
    "wv": "54",
    "wi": "55",
    "wy": "56",
}


def normalize_place_key(place_id: str, warnings: List[str], level: Optional[str] = None) -> str:
    """
    Normalize a place identifier to a join/map ``place_key`` (usually a Data Commons DCID).

    When ``level`` is ``zip`` or ``zcta``, 5-digit codes use ``zip/<zcta>`` (required for
    Data Commons GeoJSON). Bare 5-digit codes without a level default to ``geoId/<fips>``
    (county-oriented legacy behavior).
    """
    s = str(place_id).strip()
    if not s:
        warnings.append("Encountered empty place id; skipping.")
        return ""
    lvl = str(level or "").strip().lower()
    zip_level = lvl in ("zip", "zcta")

    if "/" in s:
        if zip_level and s.lower().startswith("geoid/"):
            tail = s.split("/", 1)[1].strip()
            if tail.isdigit() and len(tail) == 5:
                warnings.append(
                    f"ZIP-level request: converted {s!r} to zip/{tail} for Data Commons ZCTA geometry."
                )
                return f"zip/{tail}"
        return s

    if s.isdigit() and len(s) == 5 and zip_level:
        return f"zip/{s}"
    if s.isdigit() and len(s) in (2, 5, 7, 10):
        return f"geoId/{s}"
    if s.isdigit():
        warnings.append(f"Ambiguous numeric place id {s!r}; leaving place_key as {s!r} (not a DC geoId).")
        return s
    warnings.append(
        f"Non-DC place identifier {s!r} could not be normalized deterministically; joins/maps may fail."
    )
    return s


def place_level_to_dc_children_type(level: str) -> Optional[str]:
    return {
        "country": "Country",
        "state": "State",
        "county": "County",
        "city": "City",
        "tract": "CensusTract",
        "zip": "ZipCodeTabulationArea",
        "cbsa": "CBSA",
        "hsa": "HospitalServiceArea",
        "other": None,
    }.get(level)


def resolve_within_to_parent_dcid(within: str, warnings: List[str]) -> Optional[str]:
    """
    Resolve `within` to a parent place DCID when possible:
    - Pass through values that already look like DCIDs (contain '/').
    - Map US state full name or postal abbreviation to geoId/<stateFips>.
    """
    w = str(within).strip()
    if not w:
        return None
    if "/" in w:
        return w

    wl = w.strip().lower()
    # Support US parent queries like "United States", "US", "USA".
    # Keep this deterministic: map to the well-known Data Commons DCID for the US.
    if wl in ("united states", "united states of america", "usa", "us", "u.s.", "u.s.a."):
        return "country/USA"

    wl = wl.replace("usa", "").replace("united states", "").strip(" ,")
    if wl in _US_STATE_TO_FIPS:
        return f"geoId/{_US_STATE_TO_FIPS[wl]}"
    if wl in _US_ABBR_TO_FIPS:
        return f"geoId/{_US_ABBR_TO_FIPS[wl]}"

    warnings.append(
        f"Unable to resolve within={within!r} to a parent DCID. "
        "Supported: a parent DCID (e.g. geoId/39025) or US state name/abbr (e.g. Indiana, IN)."
    )
    return None


def _dc_api_key() -> Optional[str]:
    return os.environ.get("DC_API_KEY") or os.environ.get("DATACOMMONS_API_KEY")


def _get_v2_client():  # type: ignore[no-untyped-def]
    try:
        from datacommons_client.client import DataCommonsClient
    except ImportError:
        return None
    key = _dc_api_key()
    if not key:
        return None
    return DataCommonsClient(api_key=key)


def _extract_dcids_from_v2_node_payload(result: Any, parent_dcid: str) -> List[str]:
    if not isinstance(result, dict):
        return []
    chunk = result.get(parent_dcid)
    if chunk is None:
        return []
    out: List[str] = []
    if isinstance(chunk, list):
        for item in chunk:
            if isinstance(item, dict) and item.get("dcid"):
                out.append(str(item["dcid"]))
        return out
    if isinstance(chunk, dict):
        for item in chunk.values():
            if isinstance(item, dict) and item.get("dcid"):
                out.append(str(item["dcid"]))
            elif isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict) and sub.get("dcid"):
                        out.append(str(sub["dcid"]))
        return out
    return out


def looks_like_us_county_dcid(dcid: str) -> bool:
    """US county DCIDs are typically geoId/ + 5-digit FIPS (e.g. geoId/39025)."""
    if not dcid.startswith("geoId/"):
        return False
    tail = dcid.split("/", 1)[1]
    return tail.isdigit() and len(tail) == 5


def fetch_place_children_v2(parent_dcid: str, children_type: str, warnings: List[str]) -> List[str]:
    client = _get_v2_client()
    if client is None:
        if not _dc_api_key():
            warnings.append(
                "DC_API_KEY (or DATACOMMONS_API_KEY) is required for Data Commons v2 place expansion; "
                "the v1 containment API is deprecated (HTTP 410)."
            )
        else:
            warnings.append(
                "Install datacommons-client for v2 place expansion: pip install datacommons-client"
            )
        return []
    try:
        result = client.node.fetch_place_children(
            place_dcids=[parent_dcid],
            children_type=children_type,
            as_dict=True,
        )
    except Exception as e:
        warnings.append(f"Data Commons v2 fetch_place_children failed: {e}")
        return []
    return _extract_dcids_from_v2_node_payload(result, parent_dcid)


def fetch_place_descendants_v2(parent_dcid: str, descendants_type: str, warnings: List[str]) -> List[str]:
    client = _get_v2_client()
    if client is None:
        return []
    try:
        result = client.node.fetch_place_descendants(
            place_dcids=[parent_dcid],
            descendants_type=descendants_type,
            as_tree=False,
        )
    except Exception as e:
        warnings.append(f"Data Commons v2 fetch_place_descendants failed: {e}")
        return []
    return _extract_dcids_from_v2_node_payload(result, parent_dcid)


def expand_places_for_parent_and_level(
    *,
    level: str,
    within: Optional[str],
    explicit_ids: Optional[List[str]],
    warnings: List[str],
) -> List[str]:
    """
    Return place DCIDs for maps/observations.

    - If explicit_ids is non-empty, normalize and return those (no expansion).
    - Else if within is set, resolve parent then list children of `level` under that parent via v2 API.
    - For city level under a US county parent, if direct children are empty, fall back to descendants_type City.
    """
    ids_in = [str(x).strip() for x in (explicit_ids or []) if str(x).strip()]
    if ids_in:
        out: List[str] = []
        for pid in ids_in:
            pk = normalize_place_key(pid, warnings, level=level)
            if pk:
                out.append(pk)
        return out

    if not within:
        return []

    parent = resolve_within_to_parent_dcid(within, warnings)
    if not parent:
        return []

    ct = place_level_to_dc_children_type(level)
    if not ct:
        warnings.append(f"Cannot expand places for level={level!r} (unsupported for containment).")
        return []

    kids = fetch_place_children_v2(parent, ct, warnings)

    if (
        not kids
        and level == "city"
        and looks_like_us_county_dcid(parent)
        and ct == "City"
    ):
        warnings.append(
            "No direct child places of type City; trying descendants of type City under this county (v2 API)."
        )
        kids = fetch_place_descendants_v2(parent, "City", warnings)

    return kids
