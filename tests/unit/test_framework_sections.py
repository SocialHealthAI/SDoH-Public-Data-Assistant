"""Heading resolve for propose_data_inventory_assessment_update."""
from framework_sections import (
    UNKNOWN_HEADING_MESSAGE,
    resolve_framework_heading,
)


def test_resolve_canonical_and_aliases():
    assert resolve_framework_heading("2. Data Inventory") == "2. Data Inventory"
    assert resolve_framework_heading("## 3. Data Assessment") == "3. Data Assessment"
    assert resolve_framework_heading("2") == "2. Data Inventory"
    assert resolve_framework_heading("pd") == "1. Problem Definition"


def test_resolve_unknown_heading():
    assert resolve_framework_heading("not a section") is None
    assert resolve_framework_heading("") is None
    assert "propose_data_inventory_assessment_update" in UNKNOWN_HEADING_MESSAGE
