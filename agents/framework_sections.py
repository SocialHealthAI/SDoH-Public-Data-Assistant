"""Canonical AI Solution Requirements Definition section headings."""
from __future__ import annotations

import re

from sdoh_core.document_section_tool import default_heading_match

FRAMEWORK_SECTIONS = (
    "1. Problem Definition",
    "2. Data Inventory",
    "3. Data Assessment",
    "4. AI Approach Recommendation",
    "5. Operational Requirements",
)

_ALIASES = {
    "1": "1. Problem Definition",
    "pd": "1. Problem Definition",
    "2": "2. Data Inventory",
    "3": "3. Data Assessment",
    "4": "4. AI Approach Recommendation",
    "5": "5. Operational Requirements",
}

UNKNOWN_HEADING_MESSAGE = (
    "propose_data_inventory_assessment_update section_heading must be one of: "
    "1. Problem Definition, 2. Data Inventory, 3. Data Assessment, "
    "4. AI Approach Recommendation, 5. Operational Requirements. "
    "Call again with a recognized heading and a non-empty section_body."
)


def _normalize_heading(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^#+\s*", "", text)
    return text.strip()


def resolve_framework_heading(raw: str) -> str | None:
    heading = _normalize_heading(raw)
    if not heading:
        return None
    lowered = heading.lower()
    if lowered in _ALIASES:
        return _ALIASES[lowered]
    for canonical in FRAMEWORK_SECTIONS:
        if default_heading_match(canonical, heading):
            return canonical
    return None
