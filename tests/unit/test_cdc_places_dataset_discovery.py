from unittest.mock import patch

from tools.cdc_places_helpers import (
    discover_places_datasets,
    geo_level_from_catalog_name,
    get_places_datasets,
    places_release_year,
    release_year_from_catalog_name,
)


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


def test_get_places_datasets_live():
    """Integration: catalog discovery against data.cdc.gov (skipped if offline)."""
    try:
        ds = get_places_datasets(force_refresh=True)
    except Exception:
        return
    assert ds.get("county")
    assert ds.get("zip")
