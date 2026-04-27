"""Shared constants and utility functions for the FlashMC collimator creator.

This module is imported by cerrobend_holder.py, cerrobend_mold.py, degrader.py,
and CC_app.py. It contains no GUI (wx) dependencies so the build modules
can be used independently of the GUI.
"""

import json  # for loading custom aperture JSON files
import logging  # for consistent logging across all modules

import build123d as bd  # CAD kernel used by all builders
import numpy as np  # needed for mesh vertex/face arrays in view_cad_object
import pyvista as pv  # 3D visualization mesh format
from build123d import Mesher  # STL import/export engine
from OCP.BRep import BRep_Tool  # extracts triangulation from OCP faces
from OCP.BRepMesh import BRepMesh_IncrementalMesh  # tessellates CAD solids for viewing
from OCP.TopLoc import TopLoc_Location  # applies coordinate transforms to mesh nodes

# ---------------------------------------------------------------------------
# Logging — one shared config so every module writes to the same log file
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename="cad_viewer.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ---------------------------------------------------------------------------
# Default dimensions (mm) — used as fallback values throughout the app
# ---------------------------------------------------------------------------
LENGTH_DEFAULT = 123.0  # holder box length (X direction)
WIDTH_DEFAULT = 117.5  # holder box width (Y direction)
THICKNESS_DEFAULT = 18.0  # holder box height (Z); increased from 14 for thicker mold walls
WALL_DEFAULT = 2.0  # holder shell wall thickness
RECTANGLE_WIDTH_DEFAULT = 1.2  # width of the tab extrusions on holder faces
RECTANGLE_HEIGHT_DEFAULT = 100.0  # height of the tab extrusions on holder faces

# ---------------------------------------------------------------------------
# Offset defaults (mm) — shifts rails and stopper, NOT the aperture
# ---------------------------------------------------------------------------
OFFSET_X_DEFAULT = 0.0  # crossline (X) offset for rails/stopper
OFFSET_Y_DEFAULT = 0.0  # inline (Y) offset for rails/stopper

# ---------------------------------------------------------------------------
# Aperture defaults (mm) — define the beam-shaping opening
# ---------------------------------------------------------------------------
APERTURE_RADIUS_DEFAULT = 10.0  # radius when aperture shape is Circular
APERTURE_WIDTH_DEFAULT = 15.0  # crossline width when shape is Rectangular
APERTURE_HEIGHT_DEFAULT = 15.0  # inline height when shape is Rectangular

# ---------------------------------------------------------------------------
# Rail and stopper defaults (mm) — mouse jig positioning hardware
# ---------------------------------------------------------------------------
RAIL_DISTANCE_DEFAULT = 30.2  # center-to-center distance between the two rails
RAIL_LENGTH_DEFAULT = 90.0  # how long each rail extends in Y
RAIL_WIDTH_DEFAULT = 3.8  # width of each rail in X
STOPPER_SIZE_DEFAULT = 2.0  # size of the positioning stopper block

# ---------------------------------------------------------------------------
# Fixed geometry parameters — not exposed in the GUI
# ---------------------------------------------------------------------------
FILLET_RADIUS = 5.0  # fillet radius on vertical edges of holder and mold
WALL_THICKNESS = 6  # mold shell wall thickness (thicker than holder wall)
APERTURE_EXTRUDE_AMOUNT = 13  # base extrusion depth for the mold aperture column
MESH_QUALITY = 0.1  # tessellation resolution for PyVista viewing (lower = finer)


# ---------------------------------------------------------------------------
# Shared aperture sketch helper
# ---------------------------------------------------------------------------
def add_aperture_to_sketch(
    aperture_shape,
    aperture_radius=None,
    aperture_width=None,
    aperture_height=None,
    custom_aperture_points=None,
):
    """Draw aperture geometry into the currently active BuildSketch context.

    This must be called from *inside* a ``with bd.BuildSketch(...):`` block.
    It dispatches to the correct build123d primitive based on the shape string.

    Args:
        aperture_shape: One of "Circular", "Rectangular", or "Custom".
        aperture_radius: Radius for circular apertures.
        aperture_width: Width (X) for rectangular apertures.
        aperture_height: Height (Y) for rectangular apertures.
        custom_aperture_points: List of (x, y) tuples for custom polygon apertures.
    """
    if aperture_shape == "Circular":
        # Draw a circle centered at the sketch origin
        bd.Circle(aperture_radius)
    elif aperture_shape == "Rectangular":
        # Draw a rectangle centered at the sketch origin
        bd.Rectangle(aperture_width, aperture_height)
    else:  # Custom polygon
        # Validate that we actually have points to work with
        if not custom_aperture_points or len(custom_aperture_points) < 3:
            raise ValueError("Custom aperture requires at least 3 coordinate points")
        # bd.Polygon takes each point as a separate positional argument
        bd.Polygon(*custom_aperture_points)


# ---------------------------------------------------------------------------
# Mesh conversion for PyVista viewing
# ---------------------------------------------------------------------------
def view_cad_object(part):
    """Convert a build123d Part or Solid into a PyVista PolyData mesh.

    Tessellates the CAD solid using OCP's incremental mesher, then extracts
    the triangle vertices and face connectivity into a format PyVista can render.

    Args:
        part: A build123d Part or Solid object.

    Returns:
        pv.PolyData mesh suitable for adding to a PyVista plotter.
    """
    # Tessellate the OCP shape at the configured quality level
    mesh = BRepMesh_IncrementalMesh(
        part.wrapped, MESH_QUALITY, False, MESH_QUALITY, True
    )
    mesh.Perform()

    # Collect all vertices and triangle faces across every face of the part
    vertices = []
    faces = []
    offset = 0  # running index offset as we accumulate vertices from each face

    for face in part.faces():
        loc = TopLoc_Location()
        # Get the triangulation data for this face
        poly = BRep_Tool.Triangulation_s(face.wrapped, loc)
        if poly is None:
            continue  # skip faces that couldn't be triangulated

        # Get the coordinate transform for this face
        trsf = loc.Transformation()

        # Extract and transform each vertex
        verts = []
        for i in range(1, poly.NbNodes() + 1):
            p = poly.Node(i)
            p_transformed = p.Transformed(trsf)  # apply face's local transform
            verts.append([p_transformed.X(), p_transformed.Y(), p_transformed.Z()])
        vertices.extend(verts)

        # Extract triangle connectivity (OCP uses 1-based indexing)
        for i in range(1, poly.NbTriangles() + 1):
            n1, n2, n3 = poly.Triangle(i).Get()
            # PyVista face format: [num_points, idx0, idx1, idx2]
            faces.extend([3, offset + n1 - 1, offset + n2 - 1, offset + n3 - 1])

        offset += len(verts)  # advance the index offset for the next face

    # Build and return the PyVista mesh
    return pv.PolyData(np.array(vertices), np.array(faces))


# ---------------------------------------------------------------------------
# STL export
# ---------------------------------------------------------------------------
def export_stl_file(part, filename):
    """Export a build123d part to a binary STL file.

    Args:
        part: A build123d Part or Solid object.
        filename: Output file path (should end in .stl).

    Raises:
        Exception: If the export fails (caller is responsible for UI feedback).
    """
    try:
        bd.export_stl(part, filename)
        logging.info(f"STL file exported: {filename}")
    except Exception as e:
        logging.error(f"Error exporting STL file {filename}: {str(e)}")
        raise  # re-raise so the GUI layer can show a message box


# ---------------------------------------------------------------------------
# STL import
# ---------------------------------------------------------------------------
def import_stl(file_path):
    """Import an STL file and return a build123d Solid.

    Uses build123d's Mesher to read the STL and convert the first shape
    into a Solid object.

    Args:
        file_path: Path to the .stl file.

    Returns:
        A build123d Solid, or None if the import failed or file was empty.
    """
    try:
        importer = Mesher()
        imported_shapes = importer.read(file_path)
        logging.info(
            f"STL import: {importer.mesh_count=}, {importer.vertex_counts=}, "
            f"{importer.triangle_counts=}"
        )
        logging.info(f"Imported model unit: {importer.model_unit}")
        if imported_shapes:
            # Mesher may return a Shape that isn't a Solid; wrap it if needed
            return (
                bd.Solid(imported_shapes[0])
                if not isinstance(imported_shapes[0], bd.Solid)
                else imported_shapes[0]
            )
        return None
    except Exception as e:
        logging.error(f"Error importing STL file: {str(e)}")
        return None


# ---------------------------------------------------------------------------
# Custom aperture JSON loader
# ---------------------------------------------------------------------------
def load_custom_aperture_points(json_path):
    """Load custom aperture polygon points from a JSON file.

    The JSON file must contain a list of at least 3 coordinate pairs,
    e.g. [[0, 0], [10, 0], [10, 10], [0, 10]].

    Args:
        json_path: Path to the JSON file.

    Returns:
        List of (x, y) float tuples.

    Raises:
        ValueError: If the path is empty or the data is malformed.
    """
    # Guard against empty path (e.g. user forgot to select a file)
    if not json_path:
        raise ValueError("No JSON file path provided for custom aperture")

    # Read and parse the JSON file
    with open(json_path, "r") as f:
        data = json.load(f)

    # Validate top-level structure: must be a list with at least 3 points
    if not isinstance(data, list) or len(data) < 3:
        raise ValueError("JSON must contain a list of at least 3 coordinate pairs")

    # Convert each [x, y] pair to a (float, float) tuple
    points = []
    for point in data:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("Each point must be a list of 2 coordinates [x, y]")
        points.append((float(point[0]), float(point[1])))

    return points
