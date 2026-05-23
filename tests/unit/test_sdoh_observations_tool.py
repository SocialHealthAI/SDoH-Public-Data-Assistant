import pytest

pytest.importorskip("langchain")
try:
    from langchain.tools import StructuredTool  # noqa: F401
except ImportError:
    pytest.skip("langchain.tools.StructuredTool not available", allow_module_level=True)

from unittest.mock import patch

from tools.sdoh_observations_tool import (
    OutputRequest,
    PlaceRequest,
    SdohObservationsTool,
    TimeRequest,
)

CMS_DATASET_UUID = "00000000-0000-0000-0000-000000000001"


class _StubTool:
    pass


def _make_obs_tool() -> SdohObservationsTool:
    return SdohObservationsTool(dc_observations_tool=_StubTool())


def _observation_rows(out: dict) -> list:
    data = out["data"]
    if isinstance(data, list):
        return data
    return data.get("rows", [])


def _places_row(
    *,
    locationid: str,
    year: str,
    measureid: str = "LONELINESS",
    data_value: str = "14.2",
) -> dict:
    return {
        "locationid": locationid,
        "locationname": "Test Place",
        "year": year,
        "data_value": data_value,
        "data_value_unit": "%",
        "data_value_type": "Age-adjusted prevalence",
        "datavaluetypeid": "AgeAdjPrv",
        "measureid": measureid,
        "datasource": "BRFSS",
        "category": "Health-Related Social Needs",
    }


def _cms_page(rows, *, offset=0, size=500):
    if offset == 0:
        return rows
    return []


@patch("tools.sdoh_observations_tool._cms_fetch_rows")
def test_cms_county_place_key(mock_cms_fetch):
    county_row = {
        "Year": 2023,
        "Prscrbr_Geo_Lvl": "County",
        "Prscrbr_Geo_Cd": "39061",
        "Rate": 12.5,
    }
    mock_cms_fetch.side_effect = lambda dataset_uuid, offset=0, size=500: _cms_page(
        [county_row], offset=offset, size=size
    )
    tool = _make_obs_tool()
    out = tool._run(
        indicators=[f"cms:{CMS_DATASET_UUID}"],
        place=PlaceRequest(level="county", ids=["geoId/39061"]),
        time=TimeRequest(year=2023),
        sources=["cms"],
    )
    rows = _observation_rows(out)
    assert len(rows) == 1
    assert rows[0]["place_key"] == "geoId/39061"
    assert rows[0]["year"] == 2023
    assert rows[0]["source"] == "cms"
    assert rows[0]["value"] == 12.5


@patch("tools.sdoh_observations_tool._cms_fetch_rows")
def test_cms_zip_place_key(mock_cms_fetch):
    zip_row = {
        "Year": 2023,
        "Prscrbr_Geo_Lvl": "ZIP",
        "Prscrbr_Geo_Cd": "45202",
        "Rate": 3.1,
    }
    mock_cms_fetch.side_effect = lambda dataset_uuid, offset=0, size=500: _cms_page(
        [zip_row], offset=offset, size=size
    )
    tool = _make_obs_tool()
    out = tool._run(
        indicators=[f"cms:{CMS_DATASET_UUID}"],
        place=PlaceRequest(level="zip", ids=["45202"]),
        time=TimeRequest(year=2023),
        sources=["cms"],
    )
    rows = _observation_rows(out)
    assert len(rows) == 1
    assert rows[0]["place_key"] == "zip/45202"
    assert rows[0]["source"] == "cms"


@patch("tools.sdoh_observations_tool.dataset_id_for_geo_level", return_value="mock-tract-dataset")
@patch("tools.sdoh_observations_tool.fetch_places_observations_batched")
def test_cdcplaces_tract_row(mock_fetch, _mock_dataset):
    mock_fetch.return_value = [_places_row(locationid="39061000200", year="2023")]
    tool = _make_obs_tool()
    out = tool._run(
        indicators=["cdcplaces:tract/LONELINESS/AgeAdjPrv"],
        place=PlaceRequest(level="tract", ids=["geoId/39061000200"]),
        time=TimeRequest(year=2023),
        sources=["cdcplaces"],
    )
    rows = _observation_rows(out)
    assert len(rows) == 1
    assert rows[0]["place_key"] == "geoId/39061000200"
    assert rows[0]["source"] == "cdcplaces"


@patch("tools.sdoh_observations_tool.dataset_id_for_geo_level", return_value="mock-county-dataset")
@patch("tools.sdoh_observations_tool.fetch_places_observations_batched")
def test_cdcplaces_year_filter(mock_fetch, _mock_dataset):
    mock_fetch.return_value = [
        _places_row(locationid="18001", year="2022", data_value="10.0"),
        _places_row(locationid="18001", year="2023", data_value="14.2"),
    ]
    tool = _make_obs_tool()
    out = tool._run(
        indicators=["cdcplaces:county/LONELINESS/AgeAdjPrv"],
        place=PlaceRequest(level="county", ids=["geoId/18001"]),
        time=TimeRequest(year=2023),
        sources=["cdcplaces"],
    )
    rows = _observation_rows(out)
    assert len(rows) == 1
    assert rows[0]["year"] == 2023
    assert rows[0]["value"] == 14.2


@patch("tools.sdoh_observations_tool.dataset_id_for_geo_level", return_value="mock-county-dataset")
@patch("tools.sdoh_observations_tool.fetch_places_observations_batched")
def test_auto_wide_default_for_multiple_indicators(mock_fetch, _mock_dataset):
    def _fetch_side_effect(**kwargs):
        measure = kwargs.get("measure_id")
        if measure == "LONELINESS":
            return [_places_row(locationid="18001", year="2023", measureid="LONELINESS", data_value="14.2")]
        return [_places_row(locationid="18001", year="2023", measureid="DIABETES", data_value="8.1")]

    mock_fetch.side_effect = _fetch_side_effect
    tool = _make_obs_tool()
    ind_lonely = "cdcplaces:county/LONELINESS/AgeAdjPrv"
    ind_diabetes = "cdcplaces:county/DIABETES/AgeAdjPrv"
    out = tool._run(
        indicators=[ind_lonely, ind_diabetes],
        place=PlaceRequest(level="county", ids=["geoId/18001"]),
        time=TimeRequest(year=2023),
        sources=["cdcplaces"],
    )
    rows = _observation_rows(out)
    assert len(rows) == 1
    assert ind_lonely in rows[0] and ind_diabetes in rows[0]
    assert out["join_status"]["join_succeeded"] is True
    assert "long; join not materialized" not in " ".join(out.get("warnings", []))


@patch("tools.sdoh_observations_tool.dataset_id_for_geo_level", return_value="mock-county-dataset")
@patch("tools.sdoh_observations_tool.fetch_places_observations_batched")
def test_wide_join_two_indicators(mock_fetch, _mock_dataset):
    def _fetch_side_effect(**kwargs):
        measure = kwargs.get("measure_id")
        if measure == "LONELINESS":
            return [_places_row(locationid="18001", year="2023", measureid="LONELINESS", data_value="14.2")]
        return [_places_row(locationid="18001", year="2023", measureid="DIABETES", data_value="8.1")]

    mock_fetch.side_effect = _fetch_side_effect
    tool = _make_obs_tool()
    ind_lonely = "cdcplaces:county/LONELINESS/AgeAdjPrv"
    ind_diabetes = "cdcplaces:county/DIABETES/AgeAdjPrv"
    out = tool._run(
        indicators=[ind_lonely, ind_diabetes],
        place=PlaceRequest(level="county", ids=["geoId/18001"]),
        time=TimeRequest(year=2023),
        output=OutputRequest(format="wide"),
        sources=["cdcplaces"],
    )
    rows = _observation_rows(out)
    assert len(rows) == 1
    row = rows[0]
    assert row["place_key"] == "geoId/18001"
    assert row["year"] == 2023
    assert row[ind_lonely] == 14.2
    assert row[ind_diabetes] == 8.1
    assert out["join_status"]["join_succeeded"] is True


@patch("tools.sdoh_observations_tool.dataset_id_for_geo_level", return_value="mock-county-dataset")
@patch("tools.sdoh_observations_tool.fetch_places_observations_batched")
def test_cdcplaces_county_observations(mock_fetch, _mock_dataset):
    mock_fetch.return_value = [_places_row(locationid="18001", year="2023")]
    tool = _make_obs_tool()
    out = tool._run(
        indicators=["cdcplaces:county/LONELINESS/AgeAdjPrv"],
        place=PlaceRequest(level="county", ids=["geoId/18001"]),
        time=TimeRequest(year=2023),
        sources=["cdcplaces"],
    )
    rows = _observation_rows(out)
    assert len(rows) == 1
    assert rows[0]["place_key"] == "geoId/18001"
    assert rows[0]["year"] == 2023
    assert rows[0]["value"] == 14.2
    assert rows[0]["source"] == "cdcplaces"
