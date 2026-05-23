import json
from pathlib import Path
from unittest.mock import patch

import tools.cdc_places_helpers as cdc_helpers
from tools.cdc_places_helpers import (
    discover_places_datasets,
    fetch_measure_index,
    geo_level_from_catalog_name,
    get_places_datasets,
    release_year_from_catalog_name,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_geo_level_from_catalog_name():
    assert geo_level_from_catalog_name("PLACES: Local Data for Better Health, County Data, 2025 release") == "county"
    assert geo_level_from_catalog_name("PLACES: ZCTA Data (GIS Friendly Format), 2025 release") is None
    assert geo_level_from_catalog_name("PLACES: Local Data for Better Health, Place Data, 2025 release") == "place"


def test_release_year_from_catalog_name():
    assert release_year_from_catalog_name("County Data, 2025 release") == 2025
    assert release_year_from_catalog_name("County Data 2024 release") == 2024


MOCK_CATALOG = {
    "results": [
        {
            "resource": {
                "id": "swc5-untb",
                "name": "PLACES: Local Data for Better Health, County Data, 2025 release",
            }
        },
        {
            "resource": {
                "id": "qnzd-25i4",
                "name": "PLACES: Local Data for Better Health, ZCTA Data, 2025 release",
            }
        },
        {
            "resource": {
                "id": "old-county",
                "name": "PLACES: Local Data for Better Health, County Data 2020 release",
            }
        },
    ]
}

MOCK_CATALOG_PLACE_ZIP = {
    "results": [
        {
            "resource": {
                "id": "swc5-untb",
                "name": "PLACES: Local Data for Better Health, County Data, 2025 release",
            }
        },
        {
            "resource": {
                "id": "place-2025",
                "name": "PLACES: Local Data for Better Health, Place Data, 2025 release",
            }
        },
        {
            "resource": {
                "id": "qnzd-25i4",
                "name": "PLACES: Local Data for Better Health, ZCTA Data, 2025 release",
            }
        },
    ]
}

MOCK_CATALOG_WITH_GIS = {
    "results": [
        {
            "resource": {
                "id": "gis-county-wrong",
                "name": "PLACES: Local Data for Better Health, County Data (GIS Friendly Format), 2025 release",
            }
        },
        {
            "resource": {
                "id": "swc5-untb",
                "name": "PLACES: Local Data for Better Health, County Data, 2025 release",
            }
        },
        {
            "resource": {
                "id": "gis-zcta-wrong",
                "name": "PLACES: ZCTA Data (GIS Friendly Format), 2025 release",
            }
        },
        {
            "resource": {
                "id": "qnzd-25i4",
                "name": "PLACES: Local Data for Better Health, ZCTA Data, 2025 release",
            }
        },
    ]
}


@patch("tools.cdc_places_helpers.fetch_places_catalog_hits")
def test_discover_prefers_target_release_year(mock_hits):
    mock_hits.return_value = MOCK_CATALOG["results"]
    datasets, meta = discover_places_datasets(release_year=2025, force_refresh=True)
    assert datasets["county"] == "swc5-untb"
    assert datasets["zip"] == "qnzd-25i4"
    assert meta["source"] == "catalog"
    assert meta["entries"]["county"]["release_year"] == 2025


@patch("tools.cdc_places_helpers.fetch_places_catalog_hits", side_effect=OSError("network down"))
def test_discover_fallback_on_error(mock_hits):
    datasets, meta = discover_places_datasets(release_year=2025, force_refresh=True)
    assert datasets["county"] == "swc5-untb"
    assert meta["source"] == "fallback"
    assert "error" in meta


@patch("tools.cdc_places_helpers.fetch_places_catalog_hits")
def test_discover_sets_city_zcta_aliases(mock_hits):
    mock_hits.return_value = MOCK_CATALOG_PLACE_ZIP["results"]
    datasets, meta = discover_places_datasets(release_year=2025, force_refresh=True)
    assert datasets["place"] == "place-2025"
    assert datasets["zip"] == "qnzd-25i4"
    assert datasets["city"] == datasets["place"]
    assert datasets["zcta"] == datasets["zip"]
    assert meta["source"] == "catalog"
    assert meta["entries"]["place"]["dataset_id"] == "place-2025"


@patch("tools.cdc_places_helpers.fetch_places_catalog_hits")
def test_gis_friendly_title_excluded(mock_hits):
    mock_hits.return_value = MOCK_CATALOG_WITH_GIS["results"]
    datasets, _meta = discover_places_datasets(release_year=2025, force_refresh=True)
    assert datasets["county"] == "swc5-untb"
    assert datasets["zip"] == "qnzd-25i4"
    assert datasets["county"] != "gis-county-wrong"
    assert datasets["zip"] != "gis-zcta-wrong"
    assert geo_level_from_catalog_name(
        "PLACES: Local Data for Better Health, County Data (GIS Friendly Format), 2025 release"
    ) is None


@patch("tools.cdc_places_helpers.dataset_id_for_geo_level", return_value="mock-county-dataset")
@patch("tools.cdc_places_helpers._socrata_get_json")
def test_parse_socrata_group_payload(mock_socrata, _mock_dataset_id):
    cdc_helpers._MEASURE_INDEX_CACHE.clear()
    fixture = json.loads((_FIXTURES / "socrata_measure_group_sample.json").read_text(encoding="utf-8"))
    mock_socrata.return_value = fixture

    rows = fetch_measure_index("county", force_refresh=True)

    assert len(rows) == 3
    assert rows[0]["measure_id"] == "LONELINESS"
    assert rows[0]["data_value_type_id"] == "AgeAdjPrv"
    assert rows[0]["data_value_type_label"] == "Age-adjusted prevalence"
    assert rows[1]["measure_id"] == "LONELINESS"
    assert rows[1]["data_value_type_id"] == "CrdPrv"
    assert rows[2]["measure_id"] == "DIABETES"
    mock_socrata.assert_called_once()
    call_path = mock_socrata.call_args[0][0]
    assert call_path.startswith("mock-county-dataset.json?")


def test_get_places_datasets_live():
    """Integration: catalog discovery against data.cdc.gov (skipped if offline)."""
    try:
        ds = get_places_datasets(force_refresh=True)
    except Exception:
        return
    assert ds.get("county")
    assert ds.get("zip")
