from unittest.mock import patch

import pytest

from tools.cdc_places_helpers import (
    build_indicator_id,
    extract_location_ids,
    fetch_measure_index,
    normalize_data_value_type_id,
    normalize_places_geo_level,
    parse_native_id,
    place_key_from_location_id,
    resolve_measure_id,
    search_catalog,
)


def test_normalize_data_value_type_aliases():
    assert normalize_data_value_type_id("AgeAdjPrv") == "AgeAdjPrv"
    assert normalize_data_value_type_id("age adjusted") == "AgeAdjPrv"
    assert normalize_data_value_type_id("CrdPrv") == "CrdPrv"


def test_resolve_measure_id_uppercases():
    assert resolve_measure_id("loneliness") == "LONELINESS"


def test_parse_native_id():
    geo, mid, vt = parse_native_id("county/LONELINESS/AgeAdjPrv")
    assert geo == "county"
    assert mid == "LONELINESS"
    assert vt == "AgeAdjPrv"


def test_place_key_county_zip_place():
    assert place_key_from_location_id("18001", "county") == "geoId/18001"
    assert place_key_from_location_id("01001", "zip") == "zip/01001"
    assert place_key_from_location_id("0100100", "place") == "geoId/0100100"


def test_extract_location_ids():
    w: list = []
    ids = extract_location_ids(["geoId/18001", "zip/01001"], "county", w)
    assert ids == ["18001"]
    w2: list = []
    zids = extract_location_ids(["zip/01001", "geoId/01001"], "zip", w2)
    assert zids == ["01001"]


def test_normalize_places_geo_level():
    assert normalize_places_geo_level("city") == "place"
    assert normalize_places_geo_level("zcta") == "zip"


MOCK_INDEX = [
    {
        "measure_id": "LONELINESS",
        "measure": "Loneliness among adults",
        "category": "Health-Related Social Needs",
        "data_value_type_id": "AgeAdjPrv",
        "data_value_type_label": "Age-adjusted prevalence",
    },
    {
        "measure_id": "LONELINESS",
        "measure": "Loneliness among adults",
        "category": "Health-Related Social Needs",
        "data_value_type_id": "CrdPrv",
        "data_value_type_label": "Crude prevalence",
    },
    {
        "measure_id": "DIABETES",
        "measure": "Diagnosed diabetes among adults",
        "category": "Health Outcomes",
        "data_value_type_id": "AgeAdjPrv",
        "data_value_type_label": "Age-adjusted prevalence",
    },
]


@patch("tools.cdc_places_helpers.fetch_measure_index", return_value=MOCK_INDEX)
def test_search_loneliness_socrata_index(mock_idx):
    results = search_catalog("loneliness age adjusted county", max_results=5)
    assert results
    assert results[0]["indicator_id"].endswith("LONELINESS/AgeAdjPrv")
    assert results[0]["catalog_metadata"]["discovery"] == "socrata_measure_index"
    mock_idx.assert_called_once()


@patch("tools.cdc_places_helpers.fetch_measure_index", return_value=MOCK_INDEX)
def test_search_diabetes(mock_idx):
    results = search_catalog("diabetes county", max_results=5)
    assert any("DIABETES" in r["indicator_id"] for r in results)


def test_build_indicator_id_roundtrip():
    iid = build_indicator_id("county", "FOODINSECU", "CrdPrv")
    assert iid == "cdcplaces:county/FOODINSECU/CrdPrv"
    geo, mid, vt = parse_native_id(iid.split(":", 1)[1])
    assert geo == "county" and mid == "FOODINSECU" and vt == "CrdPrv"
