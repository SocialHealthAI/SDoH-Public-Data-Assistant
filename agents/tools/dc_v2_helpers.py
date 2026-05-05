"""
Data Commons REST API v2 helpers via `datacommons-client`.

The legacy `datacommons` PyPI package is deprecated and **yanked**, so it cannot be resolved by Poetry.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

ENTITY_OBSERVATION_CHUNK = 80


def dc_api_key() -> Optional[str]:
    return os.environ.get("DC_API_KEY") or os.environ.get("DATACOMMONS_API_KEY")


def get_data_commons_client():  # -> Optional[DataCommonsClient]
    key = dc_api_key()
    if not key:
        return None
    try:
        from datacommons_client.client import DataCommonsClient
    except ImportError:
        return None
    return DataCommonsClient(api_key=key)


def _to_plain(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(x) for x in obj]
    md = getattr(obj, "model_dump", None)
    if callable(md):
        try:
            return md()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return _to_plain(vars(obj))
    return obj


def _node_data_root(resp_plain: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize v2 node payload to a map of dcid -> node object."""
    if not isinstance(resp_plain, dict):
        return {}
    data = resp_plain.get("data")
    if isinstance(data, dict):
        return data
    return resp_plain


def fetch_property_values_map(node_dcids: List[str], property_name: str) -> Dict[str, List[Any]]:
    """
    Fetch one property for many nodes; returns dcid -> list of values (same spirit as v1 get_property_values).

    v2 shape (simplified): data[dcid].arcs[prop].nodes[].value
    """
    if not node_dcids:
        return {}
    client = get_data_commons_client()
    if client is None:
        return {}
    try:
        resp = client.node.fetch_property_values(node_dcids=node_dcids, properties=property_name)
    except Exception:
        return {}
    plain = _to_plain(resp)
    root = _node_data_root(plain if isinstance(plain, dict) else {})
    out: Dict[str, List[Any]] = {}
    for dcid in node_dcids:
        node = root.get(dcid)
        if not isinstance(node, dict):
            continue
        arcs = node.get("arcs") or {}
        arc = arcs.get(property_name) or {}
        nodes = arc.get("nodes") if isinstance(arc, dict) else None
        if not isinstance(nodes, list):
            continue
        vals: List[Any] = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if "value" in n and n["value"] is not None:
                vals.append(n["value"])
            elif "dcid" in n and n["dcid"] is not None:
                vals.append(n["dcid"])
        if vals:
            out[str(dcid)] = vals
    return out


def _chunks(items: List[str], size: int) -> List[List[str]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_observations_by_entity_batch(
    entity_dcids: List[str],
    variable_dcids: List[str],
    *,
    year: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Batched statistical observations for many places × many variables (Data Commons v2).

    Uses `observation.fetch_observations_by_entity_dcid` + `to_observation_records()` so we avoid
    hundreds of per-place MCP `get_observations` round trips.

    - `year=None` uses latest observations.
    - Chunks entities to keep requests bounded.
    """
    if not entity_dcids or not variable_dcids:
        return []
    client = get_data_commons_client()
    if client is None:
        return []

    from datacommons_client.models.observation import ObservationDate

    date_arg: Any
    if year is None:
        date_arg = ObservationDate.LATEST
    else:
        date_arg = str(int(year))

    out: List[Dict[str, Any]] = []
    for chunk in _chunks([str(x).strip() for x in entity_dcids if str(x).strip()], ENTITY_OBSERVATION_CHUNK):
        try:
            # select=None => all ObservationSelect fields (includes facet metadata on each record).
            resp = client.observation.fetch_observations_by_entity_dcid(
                date_arg,
                chunk,
                variable_dcids,
                select=None,
            )
            recs = resp.to_observation_records()
        except Exception:
            continue
        for rec in recs:
            if hasattr(rec, "model_dump"):
                out.append(rec.model_dump())
            elif isinstance(rec, dict):
                out.append(rec)
    return out
