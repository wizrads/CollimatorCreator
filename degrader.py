"""Build the collimator degrader from an imported STL file.

This is the green part in the viewer — an externally designed STL model that
gets an aperture boolean-cut through its center for the beam channel.

Usage:
    from degrader import build_degrader
    part = build_degrader("path/to/model.stl", aperture_shape="Rectangular", ...)
"""

import logging  # for tracing build steps
import os  # for checking if STL file exists

import build123d as bd  # CAD kernel — needed for BuildSketch and extrude

# Import only the utilities this module needs
from utils import (
    add_aperture_to_sketch,  # shared aperture drawing helper
    import_stl,  # STL file importer
)


def build_degrader(
    stl_file_path,
    aperture_shape,
    aperture_radius=None,
    aperture_width=None,
    aperture_height=None,
    custom_aperture_points=None,  # pre-loaded list of (x, y) tuples for custom shapes
):
    """Build the collimator degrader by importing an STL and cutting an aperture.

    Loads an externally designed STL model and applies a boolean cut in the
    shape of the beam aperture. This creates the beam channel through the
    degrader material.

    No offset parameters — offsets only affect the holder's rails/stopper.

    Args:
        stl_file_path: Path to the .stl file to import.
        aperture_shape: "Circular", "Rectangular", or "Custom".
        aperture_radius: Radius for circular apertures (mm).
        aperture_width: Width for rectangular apertures (mm).
        aperture_height: Height for rectangular apertures (mm).
        custom_aperture_points: List of (x, y) tuples for custom polygon apertures.

    Returns:
        A build123d Solid with the aperture cut, or None if the STL file
        was not found or failed to import.
    """
    # Check that we have a valid STL file path
    if not stl_file_path or not os.path.exists(stl_file_path):
        logging.warning(f"STL file not found: {stl_file_path}")
        return None

    # Import the STL geometry as a build123d Solid
    part = import_stl(stl_file_path)
    if part is None:
        logging.warning(f"Failed to import STL file: {stl_file_path}")
        return None

    # Apply the aperture cut to the imported part
    try:
        # Create the aperture sketch on the XY plane at the origin
        with bd.BuildSketch() as Aperture:
            add_aperture_to_sketch(
                aperture_shape,
                aperture_radius,
                aperture_width,
                aperture_height,
                custom_aperture_points,
            )

        # Extrude the aperture sketch downward to create a cutting solid
        # 100mm is deep enough to cut through any reasonable degrader geometry
        aperture_solid_down = bd.extrude(Aperture.sketch, amount=-100)

        # Boolean subtract the aperture solid from the imported part
        modified_part = part.cut(aperture_solid_down)

        logging.info("Aperture applied to degrader successfully")
        return modified_part

    except Exception as e:
        logging.error(f"Error applying aperture to degrader: {str(e)}")
        # Return the unmodified part rather than None so the user still gets something
        return part


if __name__ == "__main__":
    from utils import APERTURE_WIDTH_DEFAULT, APERTURE_HEIGHT_DEFAULT
    import ocp_vscode as ocp

    # Change this path to an actual STL file to test
    stl_path = "path/to/your/degrader.stl"
    part = build_degrader(
        stl_file_path=stl_path,
        aperture_shape="Rectangular",
        aperture_width=APERTURE_WIDTH_DEFAULT, aperture_height=APERTURE_HEIGHT_DEFAULT,
    )
    if part:
        ocp.show_all()
    else:
        print(f"No STL file found at: {stl_path}")
