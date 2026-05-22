from tools.dc_place_expand import normalize_place_key


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
