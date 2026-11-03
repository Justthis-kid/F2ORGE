import pytest

from f2orge.charts import (
    ChartError,
    render_3d_html,
    render_3d_preview_html,
    render_table_html,
    render_table_svg,
)


TABLE = {
    "columns": [
        {"name": "time", "unit": "s"},
        {"name": "distance", "unit": "m"},
        {"name": "height", "unit": "m"},
    ],
    "rows": [["0", "0", "1"], ["1", "3", "2"], ["2", "8", "4"]],
}


@pytest.mark.parametrize(
    ("chart_type", "expected"),
    [("line", "<polyline "), ("scatter", "<circle "), ("bar", "<rect ")],
)
def test_table_chart_renders_2d_series_with_unit_labels(chart_type, expected):
    svg = render_table_svg(TABLE, chart_type, "time", ["distance", "height"])

    assert svg.startswith("<svg ")
    assert expected in svg
    assert 'data-series="0"' in svg and 'data-series="1"' in svg
    assert "time (s)" in svg and "distance (m)" in svg


def test_table_chart_rejects_bad_units_and_non_finite_values():
    bad_unit = {"columns": [{"name": "length", "unit": "not-a-unit"}], "rows": [["1"]]}
    with pytest.raises(ChartError, match="invalid unit"):
        render_table_svg(bad_unit, "line", "length", ["length"])

    bad_value = {**TABLE, "rows": [["0", "NaN", "1"]]}
    with pytest.raises(ChartError, match="finite"):
        render_table_svg(bad_value, "line", "time", ["distance"])


def test_bar_chart_accepts_text_categories_and_requires_unique_labels():
    categories = {
        "columns": [{"name": "component"}, {"name": "load", "unit": "N"}],
        "rows": [["wing", "10"], ["body", "18"]],
    }
    svg = render_table_svg(categories, "bar", "component", ["load"])
    assert "<rect " in svg and "wing" in svg and "body" in svg

    duplicates = {**categories, "rows": [["wing", "10"], ["wing", "18"]]}
    with pytest.raises(ChartError, match="must be unique"):
        render_table_svg(duplicates, "bar", "component", ["load"])


def test_table_chart_converts_compatible_series_and_rejects_mismatched_dimensions():
    converted = {
        "columns": [
            {"name": "x"}, {"name": "metric", "unit": "cm"}, {"name": "other", "unit": "m"},
        ],
        "rows": [["0", "100", "1"], ["1", "200", "2"]],
    }
    svg = render_table_svg(converted, "scatter", "x", ["metric", "other"])
    points = [part.split('cy="', 1)[1].split('"', 1)[0]
              for part in svg.split("<circle ") if 'cy="' in part]
    assert len(points) == 4 and points[0] == points[2] and points[1] == points[3]
    assert "metric (cm)" in svg

    mismatched = {
        "columns": [{"name": "x"}, {"name": "length", "unit": "m"},
                    {"name": "mass", "unit": "kg"}],
        "rows": [["0", "1", "1"]],
    }
    with pytest.raises(ChartError, match="compatible units"):
        render_table_svg(mismatched, "line", "x", ["length", "mass"])


def test_3d_scatter_and_surface_render_interactive_offline_html():
    points = render_3d_html(TABLE, "scatter3d", "time", "distance", "height")
    assert "<canvas" in points and "pointermove" in points and "wheel" in points
    assert "time (s)" in points
    preview = render_3d_preview_html(TABLE, "scatter3d", "time", "distance", "height")
    assert '<script src="/chart3d.js"></script>' in preview
    assert "pointermove" not in preview

    grid = {
        "columns": [
            {"name": "x", "unit": "m"}, {"name": "y", "unit": "m"},
            {"name": "z", "unit": "m"},
        ],
        "rows": [["0", "0", "0"], ["0", "1", "1"], ["1", "0", "2"], ["1", "1", "3"]],
    }
    surface = render_3d_html(grid, "surface3d", "x", "y", "z")
    assert '"type":"surface3d"' in surface and "faces.sort" in surface

    incomplete = {**grid, "rows": grid["rows"][:-1]}
    with pytest.raises(ChartError, match="complete grid"):
        render_3d_html(incomplete, "surface3d", "x", "y", "z")


def test_table_html_wraps_svg_in_an_offline_zoomable_page():
    page = render_table_html(render_table_svg(TABLE, "line", "time", ["distance"]), "Chart")

    assert "<title>Chart</title>" in page
    assert "addEventListener" in page
    assert "https://" not in page
