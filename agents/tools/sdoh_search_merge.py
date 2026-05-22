from __future__ import annotations

from typing import Any, Dict, List


def per_source_cap(max_results: int, source_count: int) -> int:
    """
    When multiple repositories are searched, cap each source so one catalog cannot
    consume the entire max_results budget (e.g. 10 DC + 10 CMS leaving 0 for PLACES).
    """
    n = max(1, int(source_count))
    cap = max(1, int(max_results or 20))
    if n <= 1:
        return cap
    return max(3, (cap + n - 1) // n)


def interleave_search_results(buckets: List[List[Dict[str, Any]]], max_results: int) -> List[Dict[str, Any]]:
    """Round-robin merge so every source appears in the first page of results."""
    active = [b for b in buckets if b]
    if not active:
        return []
    if len(active) == 1:
        return active[0][: max_results or 20]
    limit = max_results or 20
    out: List[Dict[str, Any]] = []
    max_len = max(len(b) for b in active)
    for i in range(max_len):
        for b in active:
            if i < len(b):
                out.append(b[i])
                if len(out) >= limit:
                    return out
    return out
