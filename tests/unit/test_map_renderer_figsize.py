import matplotlib.pyplot as plt
import pytest

pytest.importorskip("geopandas")
pytest.importorskip("shapely")

import geopandas as gpd
from shapely.geometry import box

from map_renderer import MapRenderer
from tools.geojson_tool import unwrap_antimeridian_geometry


def _boxes(coords):
    return gpd.GeoDataFrame({"geometry": [box(*c) for c in coords]})


def test_unwrap_antimeridian_shifts_positive_longitudes():
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[-179.0, 51.0], [179.5, 51.2], [179.2, 52.0], [-179.0, 51.0]]
        ],
    }
    out = unwrap_antimeridian_geometry(geom)
    xs = [p[0] for p in out["coordinates"][0]]
    assert max(xs) < 0
    assert min(xs) < -180


def test_tight_bounds_prefer_contiguous_us():
    conus = [(-120 + i, 32 + (i % 5), -119 + i, 33 + (i % 5)) for i in range(20)]
    alaska = [(-170, 60, -150, 70)]
    aleutians = [(170, 52, 179, 54)]
    gdf = _boxes(conus + alaska + aleutians)
    bounds = MapRenderer._tight_geometry_bounds(gdf)
    assert bounds is not None
    minx, _miny, maxx, _maxy = bounds
    assert minx > -130
    assert maxx < -60


def test_fit_map_view_crops_world_wide_axes():
    conus = [(-120 + i, 32 + (i % 5), -119 + i, 33 + (i % 5)) for i in range(20)]
    gdf = _boxes(conus + [(-170, 60, -150, 70), (170, 52, 179, 54)])
    fig, ax = plt.subplots(figsize=(12, 7))
    gdf.plot(ax=ax)
    ax.set_xlim(-180, 180)
    fitted = MapRenderer._fit_map_view(fig, {"gdf": gdf})
    x0, x1 = ax.get_xlim()
    plt.close(fig)
    assert fitted is True
    assert x1 < 0
    assert x1 - x0 < 80


def test_fit_leaves_colorbar_limits():
    cluster = [(-100 + i, 35, -99 + i, 36) for i in range(12)]
    gdf = _boxes(cluster)
    gdf["value"] = list(range(len(gdf)))
    fig, ax = plt.subplots(figsize=(12, 7))
    gdf.plot(column="value", ax=ax, legend=True)
    cax = fig.axes[-1]
    before = cax.get_xlim()
    MapRenderer._fit_map_view(fig, {"gdf": gdf})
    after = cax.get_xlim()
    plt.close(fig)
    assert after == before


def test_ensure_min_figsize_enlarges_small_figures():
    fig, _ax = plt.subplots(figsize=(6, 4))
    MapRenderer._ensure_min_figsize(fig)
    w, h = fig.get_size_inches()
    plt.close(fig)
    assert w >= 12.0
    assert h >= 7.0


def test_ensure_min_figsize_keeps_larger_figures():
    fig, _ax = plt.subplots(figsize=(14, 9))
    MapRenderer._ensure_min_figsize(fig)
    w, h = fig.get_size_inches()
    plt.close(fig)
    assert round(w, 4) == 14.0
    assert round(h, 4) == 9.0
