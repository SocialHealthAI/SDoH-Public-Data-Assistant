import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from tools.sdoh_observations_tool import (
    _cms_is_primary_breakout,
    _cms_pick_fields,
    _cms_place_key_from_row,
    _cms_zip_tail_from_place_id,
    _geoid_code,
    _parse_indicator_id,
)


def test_parse_indicator_id_prefixes():
    assert _parse_indicator_id("datacommons:Count_Person") == ("datacommons", "Count_Person")
    assert _parse_indicator_id("cms:12345678-1234-1234-1234-123456789abc") == (
        "cms",
        "12345678-1234-1234-1234-123456789abc",
    )
    assert _parse_indicator_id("cdcplaces:county/LONELINESS/AgeAdjPrv") == (
        "cdcplaces",
        "county/LONELINESS/AgeAdjPrv",
    )
    assert _parse_indicator_id("Count_Person") == ("datacommons", "Count_Person")


def test_cms_zip_tail_from_place_id():
    assert _cms_zip_tail_from_place_id("zip/45202") == "45202"
    assert _cms_zip_tail_from_place_id("45202") == "45202"
    assert _cms_zip_tail_from_place_id("geoId/45202") == "45202"
    # 5-digit geoId tail is treated as ZIP for CMS matching; 7-digit place FIPS is not.
    assert _cms_zip_tail_from_place_id("geoId/1800100") is None


def test_geoid_code():
    assert _geoid_code("geoId/39061") == "39061"
    assert _geoid_code("zip/45202") is None


def test_cms_place_key_from_row_county_prscrbr():
    row = {
        "Prscrbr_Geo_Lvl": "County",
        "Prscrbr_Geo_Cd": "39061",
    }
    assert (
        _cms_place_key_from_row(row, place_level="county", state_field=None, county_field=None)
        == "geoId/39061"
    )


def test_cms_is_primary_breakout():
    assert _cms_is_primary_breakout({"Breakout": "Overall"}) is True
    assert _cms_is_primary_breakout({"Breakout": "Rural"}) is False
    assert _cms_is_primary_breakout({"Breakout": "Urban"}) is False
    assert _cms_is_primary_breakout({}) is True


def test_cms_pick_fields_skips_change_columns():
    year_field, _state, _county, value_field = _cms_pick_fields(
        {
            "Year": 2024,
            "Prscrbr_Geo_Cd": "06",
            "Opioid_Prscrbng_Rate": 3.29,
            "Opioid_Prscrbng_Rate_1Y_Chg": 0.12,
            "Opioid_Prscrbng_Rate_5Y_Chg": -0.4,
        }
    )
    assert year_field == "Year"
    assert value_field == "Opioid_Prscrbng_Rate"
