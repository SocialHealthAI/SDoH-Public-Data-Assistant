from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from tools.dc_place_expand import (
    expand_places_for_parent_and_level,
    normalize_place_key,
)
from tools.dc_v2_helpers import fetch_property_values_map


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


class PlacesRequest(BaseModel):
    level: PlaceLevel = Field(..., description="Target place level to resolve.")
    ids: Optional[List[str]] = Field(
        default=None,
        description="Optional explicit place identifiers (DCIDs, FIPS, names). Deterministic resolution is applied where possible.",
    )
    within: Optional[str] = Field(
        default=None,
        description="Optional parent constraint (e.g., 'Indiana'). Supports US state names/abbreviations or a parent DCID.",
    )
    limit: Optional[int] = Field(default=None, description="Optional limit on number of resolved places returned.")


class ResolvePlacesForMapInput(BaseModel):
    places: PlacesRequest = Field(..., description="Places to resolve for map/join keys.")
    preferred_join_key: str = Field(default="place_key", description="Preferred join key (currently only place_key).")
    require_geometry: bool = Field(default=True, description="If true, ensure resolved places have DCIDs suitable for Data Commons GeoJSON.")


class ResolvePlacesForMapTool(StructuredTool):
    """
    Resolve places into Data Commons DCIDs suitable for geometry, and emit join-ready keys.

    Parent→child expansion uses Data Commons API **v2** (`fetch_place_children` via `datacommons-client`).
    Legacy v1 `get_places_in` is deprecated (HTTP 410). Requires DC_API_KEY for expansion.
    """

    def __init__(self) -> None:
        super().__init__(
            name="resolve_places_for_map",
            description=(
                "Resolve places to Data Commons DCIDs and join-ready place_key values. "
                "Uses Data Commons v2 place APIs (requires DC_API_KEY). "
                "Supports FIPS→geoId normalization, parent DCID + level expansion, and US state name/abbr as parent "
                "(e.g. within='Indiana', level='county')."
            ),
            args_schema=ResolvePlacesForMapInput,
            func=self._run,
        )

    def _run(self, places: PlacesRequest, preferred_join_key: str = "place_key", require_geometry: bool = True) -> Dict[str, Any]:
        _ = preferred_join_key  # currently fixed to place_key
        warnings: List[str] = []
        unmatched: List[Dict[str, Any]] = []
        resolved: List[Dict[str, Any]] = []

        level = places.level

        explicit_ids = [str(x).strip() for x in (places.ids or []) if str(x).strip()]
        normalized_explicit: List[str] = []
        for pid in explicit_ids:
            pk = normalize_place_key(pid, warnings)
            if not pk:
                unmatched.append({"input": pid, "reason": "empty"})
                continue
            if require_geometry and "/" not in pk:
                unmatched.append({"input": pid, "reason": "not_a_dcid"})
                continue
            normalized_explicit.append(pk)

        user_supplied_ids = places.ids is not None and len(explicit_ids) > 0
        if user_supplied_ids:
            dcids = normalized_explicit
            if not dcids:
                warnings.append("No valid place DCIDs after normalizing `places.ids`; not falling back to `within`.")
        else:
            dcids = expand_places_for_parent_and_level(
                level=str(level),
                within=places.within,
                explicit_ids=None,
                warnings=warnings,
            )

        if places.limit is not None and places.limit > 0:
            dcids = dcids[: int(places.limit)]

        name_map: Dict[str, str] = {}
        if dcids:
            vals = fetch_property_values_map(dcids, "name")
            for k, v in vals.items():
                if isinstance(v, list) and v:
                    name_map[str(k)] = str(v[0])
                elif isinstance(v, str):
                    name_map[str(k)] = v
            if not vals:
                warnings.append("Place name lookup returned no data (check DC_API_KEY and datacommons-client).")

        for dcid in dcids:
            place_key = dcid
            resolved.append(
                {
                    "place_key": place_key,
                    "place_name": name_map.get(dcid),
                    "place_level": level,
                    "dcid": dcid,
                    "dcid_norm": dcid.replace("geoId/", "", 1) if dcid.startswith("geoId/") else dcid,
                    "source_place_id": None,
                    "confidence": "high" if (dcid.startswith("geoId/") or dcid.startswith("country/")) else "medium",
                }
            )

        if not resolved and explicit_ids:
            for pid in explicit_ids:
                unmatched.append({"input": pid, "reason": "unresolved"})

        if not resolved and places.within:
            warnings.append("No places resolved. Check DC_API_KEY, parent `within` (DCID or US state), and `level`.")

        return {"resolved": resolved, "unmatched": unmatched, "warnings": warnings}
