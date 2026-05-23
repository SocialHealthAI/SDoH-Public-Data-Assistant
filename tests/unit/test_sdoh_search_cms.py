import json
from pathlib import Path

import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from tools.sdoh_search_tool import SdohSearchTool

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class _StubTool:
    pass


def _cms_tool() -> SdohSearchTool:
    return SdohSearchTool(dc_search_tool=_StubTool(), dc_observations_tool=None)


def test_extract_cms_dataset_uuid():
    entry = json.loads((_FIXTURES / "cms_catalog_snippet.json").read_text(encoding="utf-8"))
    tool = _cms_tool()
    assert tool._extract_cms_dataset_uuid(entry) == "12345678-1234-1234-1234-123456789abc"


def test_score_cms_dataset_prefers_title_match():
    entry = json.loads((_FIXTURES / "cms_catalog_snippet.json").read_text(encoding="utf-8"))
    tool = _cms_tool()
    query = "medicare part d opioid prescribing rates by geography"
    terms = query.lower().split()
    high = tool._score_cms_dataset(entry, terms, query=query)
    other = tool._score_cms_dataset(
        {"title": "Unrelated hospital quality report", "description": "hospital"},
        terms,
        query=query,
    )
    assert high > other
