from tools.dc_place_expand import (
    looks_like_us_county_dcid,
    normalize_place_key,
    resolve_within_to_parent_dcid,
)


def test_normalize_zip_level_bare_code():
    w: list = []
    assert normalize_place_key("45202", w, level="zip") == "zip/45202"


def test_normalize_zip_level_converts_geoid():
    w: list = []
    assert normalize_place_key("geoId/45202", w, level="zip") == "zip/45202"
    assert any("converted" in x.lower() for x in w)


def test_normalize_county_level_five_digit_stays_geoid():
    w: list = []
    assert normalize_place_key("18001", w, level="county") == "geoId/18001"


def test_normalize_tract_eleven_digit():
    w: list = []
    assert normalize_place_key("39025040800", w, level="tract") == "geoId/39025040800"
    assert normalize_place_key("geoId/39025040800", w, level="tract") == "geoId/39025040800"


def test_normalize_zip_rejects_geoid_on_county():
    """ZIP-style DCIDs are not converted to county geoId/FIPS when level is county."""
    w: list = []
    assert normalize_place_key("zip/01001", w, level="county") == "zip/01001"
    assert normalize_place_key("01001", w, level="county") == "geoId/01001"


def test_resolve_within_state_abbr():
    w: list = []
    assert resolve_within_to_parent_dcid("IN", w) == "geoId/18"
    assert resolve_within_to_parent_dcid("Indiana", w) == "geoId/18"


def test_resolve_within_parent_dcid_passthrough():
    w: list = []
    assert resolve_within_to_parent_dcid("geoId/39061", w) == "geoId/39061"
    assert resolve_within_to_parent_dcid("country/USA", w) == "country/USA"


def test_resolve_within_usa_aliases():
    w: list = []
    assert resolve_within_to_parent_dcid("United States", w) == "country/USA"
    assert resolve_within_to_parent_dcid("USA", w) == "country/USA"


def test_looks_like_us_county_dcid():
    assert looks_like_us_county_dcid("geoId/39061") is True
    assert looks_like_us_county_dcid("zip/45202") is False
    assert looks_like_us_county_dcid("geoId/18") is False
