from typing import List, Dict, Any
import hashlib
import json

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from tools.dc_v2_helpers import dc_api_key, fetch_property_values_map, flatten_str_ids


def unwrap_antimeridian_geometry(geom: Any) -> Any:
    """
    Shift rings that jump the antimeridian (Alaska Aleutians at +179)
    so matplotlib does not treat the layer as a world-wide extent.
    """
    if not isinstance(geom, dict):
        return geom
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Polygon" and isinstance(coords, list):
        return {**geom, "coordinates": [_unwrap_ring(ring) for ring in coords]}
    if gtype == "MultiPolygon" and isinstance(coords, list):
        return {
            **geom,
            "coordinates": [
                [_unwrap_ring(ring) for ring in poly] if isinstance(poly, list) else poly
                for poly in coords
            ],
        }
    return geom


def _unwrap_ring(ring: Any) -> Any:
    if not isinstance(ring, list) or not ring:
        return ring
    xs = []
    for p in ring:
        if isinstance(p, (list, tuple)) and p:
            try:
                xs.append(float(p[0]))
            except (TypeError, ValueError):
                continue
    if len(xs) < 2 or (max(xs) - min(xs) <= 180):
        return ring
    out = []
    for p in ring:
        if isinstance(p, (list, tuple)) and p:
            try:
                x = float(p[0])
            except (TypeError, ValueError):
                out.append(p)
                continue
            if x > 0:
                out.append([x - 360.0, *list(p[1:])])
            else:
                out.append(list(p))
        else:
            out.append(p)
    return out

try:
    import streamlit as st  # type: ignore
except Exception:  # streamlit is optional at runtime
    st = None  # type: ignore


class GeoJsonInput(BaseModel):
    """Input schema for GeoJsonTool."""

    place_dcids: List[str] = Field(
        ...,
        description=(
            "Place DCIDs to fetch geoJsonCoordinates for. When used together with "
            "the map generation tool, you MUST pass the same identifiers here as "
            "you used as region keys in the map data so that geometry and data "
            "can be joined correctly."
        ),
    )


class GeoJsonTool(StructuredTool):
    """
    Use the Data Commons API (v2 client) to fetch geoJsonCoordinates for the given set of place DCIDs
    The input descrption instructs to ReAct LLM to format the place DCIDs using the observations
    for the requested map.  We then save the geoJsonCoordinates in a session variable to be
    referenced by the map_tool and map_renderer.
    """

    def __init__(self) -> None:
        super().__init__(
            name="get_geojson_for_places",
            description=(
                "Fetch geoJsonCoordinates for a list of place DCIDs from Data Commons "
                "and return them as a GeoJSON FeatureCollection. Each feature has "
                "properties['dcid'] matching the input DCID. When used together with "
                "the map generation tool, you MUST pass the same place DCIDs that are "
                "used as region identifiers in the map data so that the geometry and "
                "tabular data can be joined correctly. Requires DC_API_KEY (Data Commons v2)."
            ),
            args_schema=GeoJsonInput,
            func=self._run,
        )

    def _run(self, place_dcids: List[str]) -> Dict[str, Any]:
        place_dcids = flatten_str_ids(place_dcids)
        if not dc_api_key():
            return {
                "geojson_ref": None,
                "feature_count": 0,
                "error": "dc_api_key_missing",
                "message": "Set DC_API_KEY (or DATACOMMONS_API_KEY) for GeoJSON via Data Commons v2.",
            }

        values = fetch_property_values_map(place_dcids, "geoJsonCoordinates")

        features = []
        for dcid in place_dcids:
            geos = values.get(dcid, []) or values.get(str(dcid), [])
            if not geos:
                continue
            for geom in geos:
                # Datacommons may return the geometry as a JSON string.
                # Ensure we always pass a proper GeoJSON geometry dict through.
                if isinstance(geom, str):
                    try:
                        geom_obj = json.loads(geom)
                    except Exception:
                        # If parsing fails, skip this geometry rather than
                        # returning an invalid feature that will break plotting.
                        continue
                else:
                    geom_obj = geom
                geom_obj = unwrap_antimeridian_geometry(geom_obj)

                # Normalized ID for robust merge: strip "geoId/" so "geoId/39035" and "39035" match
                dcid_str = str(dcid).strip()
                dcid_norm = dcid_str.replace("geoId/", "", 1) if dcid_str.startswith("geoId/") else dcid_str
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"dcid": dcid_str, "dcid_norm": dcid_norm},
                        "geometry": geom_obj,
                    }
                )

        feature_collection = {
            "type": "FeatureCollection",
            "features": features,
        }

        # Store in Streamlit session state and return only a small reference.
        # This avoids sending large GeoJSON blobs through the LLM/tool-call context.
        if st is None:
            return {
                "geojson_ref": None,
                "feature_count": len(features),
                "error": "streamlit_session_unavailable",
            }

        if "geojson_cache" not in st.session_state:
            st.session_state["geojson_cache"] = {}
        # Deterministic key for reuse across calls in the same session
        key_src = "|".join(place_dcids).encode("utf-8")
        geojson_ref = "geojson_" + hashlib.sha1(key_src).hexdigest()[:16]
        st.session_state["geojson_cache"][geojson_ref] = feature_collection
        return {
            "geojson_ref": geojson_ref,
            "feature_count": len(features),
        }
