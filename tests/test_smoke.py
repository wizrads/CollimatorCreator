import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cerrobend_holder import build_cerrobend_holder
from cerrobend_mold import build_cerrobend_mold
from utils import (
    APERTURE_HEIGHT_DEFAULT,
    APERTURE_WIDTH_DEFAULT,
    LENGTH_DEFAULT,
    RECTANGLE_HEIGHT_DEFAULT,
    RECTANGLE_WIDTH_DEFAULT,
    THICKNESS_DEFAULT,
    WALL_DEFAULT,
    WIDTH_DEFAULT,
    load_custom_aperture_points,
)


def test_core_imports():
    import build123d  # noqa: F401
    import OCP  # noqa: F401
    import pyvista  # noqa: F401
    import vtk  # noqa: F401


def test_load_custom_aperture_points(tmp_path):
    sample = [[0, 0], [10, 0], [10, 5], [0, 5]]
    json_path = tmp_path / "aperture.json"
    json_path.write_text(json.dumps(sample), encoding="utf-8")

    points = load_custom_aperture_points(str(json_path))
    assert points == [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]


def test_build_holder_and_mold_defaults():
    holder = build_cerrobend_holder(
        length=LENGTH_DEFAULT,
        width=WIDTH_DEFAULT,
        thickness=THICKNESS_DEFAULT,
        wall=WALL_DEFAULT,
        rectangle_width=RECTANGLE_WIDTH_DEFAULT,
        rectangle_height=RECTANGLE_HEIGHT_DEFAULT,
        aperture_shape="Rectangular",
        aperture_width=APERTURE_WIDTH_DEFAULT,
        aperture_height=APERTURE_HEIGHT_DEFAULT,
    )
    mold = build_cerrobend_mold(
        length=LENGTH_DEFAULT,
        width=WIDTH_DEFAULT,
        thickness=THICKNESS_DEFAULT,
        aperture_shape="Rectangular",
        aperture_width=APERTURE_WIDTH_DEFAULT,
        aperture_height=APERTURE_HEIGHT_DEFAULT,
    )

    assert holder is not None
    assert mold is not None
