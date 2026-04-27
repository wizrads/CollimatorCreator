"""Build the cerrobend mold (pour-mold with aperture extrusion column).

This is the red part in the viewer — a larger hollow box that the cerrobend
alloy is poured into. The aperture shape extrudes upward from the bottom face
to form the beam channel in the final casting.

Usage:
    from cerrobend_mold import build_cerrobend_mold
    part = build_cerrobend_mold(length=123, width=117.5, ...)
"""

import logging  # for tracing build steps

import build123d as bd  # CAD kernel

# Import only the constants and helpers this module actually needs
from utils import (
    APERTURE_EXTRUDE_AMOUNT,  # base depth of the aperture column
    FILLET_RADIUS,  # fillet radius for vertical edges
    WALL_THICKNESS,  # mold wall thickness (thicker than holder)
    add_aperture_to_sketch,  # shared aperture drawing helper
)


def build_cerrobend_mold(
    length,
    width,
    thickness,
    aperture_shape,
    aperture_radius=None,
    aperture_width=None,
    aperture_height=None,
    custom_aperture_points=None,  # pre-loaded list of (x, y) tuples for custom shapes
):
    """Build the cerrobend mold part.

    The mold is a hollow box slightly larger than the holder. The aperture
    shape is extruded upward from the bottom face to form a column that
    creates the beam channel when cerrobend is poured around it.

    No offset parameters — offsets only affect the holder's rails/stopper.

    Args:
        length: Holder box length in X (mm). Mold adds 7mm margin.
        width: Holder box width in Y (mm). Mold adds 7mm margin.
        thickness: Holder box height in Z (mm). Mold adds 3mm margin.
        aperture_shape: "Circular", "Rectangular", or "Custom".
        aperture_radius: Radius for circular apertures (mm).
        aperture_width: Width for rectangular apertures (mm).
        aperture_height: Height for rectangular apertures (mm).
        custom_aperture_points: List of (x, y) tuples for custom polygon apertures.

    Returns:
        A build123d Part object.
    """
    logging.info("Building cerrobend mold...")

    with bd.BuildPart() as CollimatorMold:
        # --- Base box ---
        # Mold is oversized by 7mm in X/Y and 3mm in Z to fit around the holder
        bd.Box(length + 7, width + 7, thickness + 3)

        # Identify the top and bottom faces by sorting along Z
        TopFace = CollimatorMold.faces().sort_by(bd.Axis.Z)[-1]
        BottomFace = CollimatorMold.faces().sort_by(bd.Axis.Z)[0]

        # --- Shell the box ---
        # Offset inward from the top face; uses WALL_THICKNESS (6mm), not the
        # holder's wall (2mm), because the mold needs to be sturdier
        bd.offset(amount=-WALL_THICKNESS, openings=TopFace)

        # --- Fillet vertical edges ---
        # Same radius as the holder for visual consistency
        bd.fillet(CollimatorMold.edges().filter_by(bd.Axis.Z), radius=FILLET_RADIUS)

        # --- Aperture column ---
        # Extrude the aperture shape upward from the bottom face to form the
        # column that the cerrobend pours around. This creates the beam channel.
        # No offset — aperture stays centered.
        with bd.BuildSketch(BottomFace) as Aperture:
            add_aperture_to_sketch(
                aperture_shape,
                aperture_radius,
                aperture_width,
                aperture_height,
                custom_aperture_points,
            )
        # Extrude upward (negative because BottomFace normal points down);
        # APERTURE_EXTRUDE_AMOUNT + 17 = 30mm total column height
        bd.extrude(amount=-(APERTURE_EXTRUDE_AMOUNT + 17), mode=bd.Mode.ADD)

        # --- Experimental: hammer tool hitting area (currently disabled) ---
        # This loft operation was intended to create a flared top on the aperture
        # column so a hammer tool could seat the cerrobend. Kept for future use.
        # aperture_top_face = CollimatorMold.faces().sort_by(bd.Axis.Z)[-1]
        # top_square_z = aperture_top_face.center().Z + 15
        # top_square_plane = bd.Plane.XY.offset(top_square_z)
        # with bd.BuildSketch(top_square_plane) as top_square:
        #     with bd.Locations((0, 0)):
        #         bd.Rectangle(30, 30)
        # bd.loft(sections=[aperture_top_face, top_square.sketch], mode=bd.Mode.ADD)

    logging.info("Cerrobend mold built successfully")
    return CollimatorMold.part


if __name__ == "__main__":
    from utils import LENGTH_DEFAULT, WIDTH_DEFAULT, THICKNESS_DEFAULT, \
        APERTURE_WIDTH_DEFAULT, APERTURE_HEIGHT_DEFAULT
    import ocp_vscode as ocp

    part = build_cerrobend_mold(
        length=LENGTH_DEFAULT, width=WIDTH_DEFAULT, thickness=THICKNESS_DEFAULT,
        aperture_shape="Rectangular",
        aperture_width=APERTURE_WIDTH_DEFAULT, aperture_height=APERTURE_HEIGHT_DEFAULT,
    )
    ocp.show_all()
