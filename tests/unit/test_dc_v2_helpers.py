from unittest.mock import MagicMock, patch

from tools.dc_v2_helpers import (
    _node_data_root,
    _to_plain,
    fetch_property_values_map,
)


def test_to_plain_model_dump():
    class _M:
        def model_dump(self):
            return {"a": 1, "b": [2]}

    assert _to_plain(_M()) == {"a": 1, "b": [2]}


def test_node_data_root_nested_data():
    assert _node_data_root({"data": {"geoId/18": {"arcs": {}}}}) == {"geoId/18": {"arcs": {}}}
    assert _node_data_root({"geoId/18": {}}) == {"geoId/18": {}}


@patch("tools.dc_v2_helpers.get_data_commons_client")
def test_fetch_property_values_map_parses_arcs(mock_client_fn):
    mock_client = MagicMock()
    mock_client_fn.return_value = mock_client
    mock_client.node.fetch_property_values.return_value = {
        "data": {
            "geoId/18001": {
                "arcs": {
                    "name": {
                        "nodes": [{"value": "Clark County, Indiana"}],
                    }
                }
            },
            "zip/45202": {
                "arcs": {
                    "name": {
                        "nodes": [{"value": "45202"}],
                    }
                }
            },
        }
    }

    out = fetch_property_values_map(["geoId/18001", "zip/45202"], "name")
    assert out["geoId/18001"] == ["Clark County, Indiana"]
    assert out["zip/45202"] == ["45202"]


@patch("tools.dc_v2_helpers.get_data_commons_client", return_value=None)
def test_fetch_property_values_map_no_client(mock_client_fn):
    assert fetch_property_values_map(["geoId/18001"], "name") == {}
