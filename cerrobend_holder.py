"""Build the cerrobend holder (mountable shell with rails and stopper).

This is the blue part in the viewer — a hollow box with tabs on three faces,
a positioning stopper, parallel rails for the mouse jig, and an aperture cut
through the center.

Usage:
    from cerrobend_holder import build_cerrobend_holder
    part = build_cerrobend_holder(length=123, width=117.5, ...)
"""

import logging  # for tracing build steps

import build123d as bd  # CAD kernel

# Import only the constants and helpers this module actually needs
from utils import (
    FILLET_RADIUS,  # fillet radius for vertical edges
    RAIL_DISTANCE_DEFAULT,  # center-to-center rail spacing
    RAIL_LENGTH_DEFAULT,  # rail extent in Y direction
    RAIL_WIDTH_DEFAULT,  # rail width in X direction
    STOPPER_SIZE_DEFAULT,  # stopper block size
    add_aperture_to_sketch,  # shared aperture drawing helper
)


def build_cerrobend_holder(
    length,
    width,
    thickness,
    wall,
    rectangle_width,
    rectangle_height,
    aperture_shape,
    aperture_radius=None,
    aperture_width=None,
    aperture_height=None,
    offset_x=0.0,  # crossline offset — only moves rails and stopper, NOT aperture
    offset_y=0.0,  # inline offset — only moves rails and stopper, NOT aperture
    custom_aperture_points=None,  # pre-loaded list of (x, y) tuples for custom shapes
):
    """Build the cerrobend holder part.

    The holder is a hollow rectangular shell with:
    - Tabs on +Y, -X, +X faces for mounting
    - A stopper block on the bottom face for positioning
    - Two parallel rails on the bottom face for the mouse jig
    - An aperture cut through the center for the beam

    Args:
        length: Box length in X (mm).
        width: Box width in Y (mm).
        thickness: Box height in Z (mm).
        wall: Shell wall thickness (mm).
        rectangle_width: Width of the tab extrusions (mm).
        rectangle_height: Height of the tab extrusions (mm).
        aperture_shape: "Circular", "Rectangular", or "Custom".
        aperture_radius: Radius for circular apertures (mm).
        aperture_width: Width for rectangular apertures (mm).
        aperture_height: Height for rectangular apertures (mm).
        offset_x: Crossline offset for rails/stopper only (mm).
        offset_y: Inline offset for rails/stopper only (mm).
        custom_aperture_points: List of (x, y) tuples for custom polygon apertures.

    Returns:
        A build123d Part object.
    """
    # Use module-level defaults for rail/stopper geometry
    rail_distance = RAIL_DISTANCE_DEFAULT
    rail_length = RAIL_LENGTH_DEFAULT
    rail_width = RAIL_WIDTH_DEFAULT
    stopper_size = STOPPER_SIZE_DEFAULT

    logging.info("Building cerrobend holder...")

    with bd.BuildPart() as CollimatorHolder:
        # --- Base box ---
        # Start with a solid rectangular block
        bd.Box(length, width, thickness)

        # Identify the top and bottom faces by sorting along Z
        TopFace = CollimatorHolder.faces().sort_by(bd.Axis.Z)[-1]
        BottomFace = CollimatorHolder.faces().sort_by(bd.Axis.Z)[0]

        # --- Shell the box ---
        # Offset inward from the top face to create hollow walls
        bd.offset(amount=-wall, openings=TopFace)

        # --- Fillet vertical edges ---
        # Round the vertical edges of the shell for structural integrity
        bd.fillet(
            CollimatorHolder.edges().filter_by(bd.Axis.Z), radius=FILLET_RADIUS
        )

        # --- Tab on +Y face ---
        # Add a rectangular tab extrusion on the positive-Y face
        positive_y_face = CollimatorHolder.faces().filter_by(bd.Axis.Y)[-1]
        with bd.BuildSketch(positive_y_face) as sketch:
            # Position the tab so it sits flush against the wall
            with bd.Locations(
                (thickness / 2 - rectangle_width / 2 - wall / 2, 0.0)
            ):
                bd.Rectangle(rectangle_width, rectangle_height)
        # Extrude inward to add material
        bd.extrude(amount=-(rectangle_width + wall), mode=bd.Mode.ADD)

        # --- Tab on -X face ---
        # Add a rectangular tab extrusion on the negative-X face
        negative_x_face = CollimatorHolder.faces().filter_by(bd.Axis.X)[-2]
        with bd.BuildSketch(negative_x_face) as sketch:
            with bd.Locations(
                (thickness / 2 - rectangle_width / 2 - wall / 2, 0.0)
            ):
                bd.Rectangle(rectangle_width, rectangle_height)
        bd.extrude(amount=-(rectangle_width + wall), mode=bd.Mode.ADD)

        # --- Tab on +X face ---
        # Add a rectangular tab extrusion on the positive-X face
        positive_x_face = CollimatorHolder.faces().filter_by(bd.Axis.X)[3]
        with bd.BuildSketch(positive_x_face) as sketch:
            with bd.Locations((thickness / 2 - rectangle_width / 2, 0.0)):
                bd.Rectangle(rectangle_width, rectangle_height)
        bd.extrude(amount=(rectangle_width), mode=bd.Mode.ADD)

        # --- Stopper on bottom face ---
        # Small block on the bottom face that positions the mouse jig
        # Offset affects stopper position so the jig aligns with the shifted rails
        negative_z_face = CollimatorHolder.faces().filter_by(bd.Axis.Z)[3]
        with bd.BuildSketch(negative_z_face) as sketch:
            # Position with offset; -48.19 is the nominal Y position of the stopper
            with bd.Locations((offset_x, -48.19 + offset_y)):
                bd.Rectangle(2 * stopper_size, stopper_size)
        # Extrude downward to protrude from the bottom face
        bd.extrude(amount=(1 + wall), mode=bd.Mode.ADD)
        # Chamfer the stopper edge for a tapered entry
        bd.chamfer(
            CollimatorHolder.edges().filter_by(bd.Axis.X)[21],
            length=1 + wall - 0.01,
        )

        # --- Main rails on bottom face ---
        # Two parallel rails that guide the mouse jig
        # Offset shifts both rails together so the jig stays aligned
        with bd.BuildSketch(negative_z_face) as sketch:
            with bd.Locations(
                (rail_distance / 2 + 2.5 + offset_x, offset_y),
                (-rail_distance / 2 - 2.5 + offset_x, offset_y),
            ):
                bd.Rectangle(rail_width, rail_length)
        # Extrude rails downward from the bottom face
        bd.extrude(amount=(4), mode=bd.Mode.ADD)

        # --- Rail grooves (subtracted from bottom face) ---
        # Narrow channels cut into the bottom face alongside the rails
        with bd.BuildSketch(negative_z_face) as sketch:
            with bd.Locations(
                (rail_distance / 2 + 2.5 / 2 + offset_x, offset_y),
                (-rail_distance / 2 - 2.5 / 2 + offset_x, offset_y),
            ):
                bd.Rectangle(2, rectangle_height)
        bd.extrude(amount=(1.7), mode=bd.Mode.SUBTRACT)

        # --- Chamfer rail tips ---
        # Taper the ends of the rails so the jig slides on smoothly
        bd.chamfer(
            CollimatorHolder.edges().filter_by(bd.Axis.Y)[2], length=4 - 0.01
        )
        bd.chamfer(
            CollimatorHolder.edges().filter_by(bd.Axis.Y)[5], length=4 - 0.01
        )

        # --- Rail clearance pockets ---
        # Larger rectangular cuts that provide clearance around the rails
        with bd.BuildSketch(negative_z_face) as sketch:
            with bd.Locations(
                (rail_distance / 2 + 2.5 / 2 + offset_x, offset_y),
                (-rail_distance / 2 - 2.5 / 2 + offset_x, offset_y),
            ):
                bd.Rectangle(30, 56.8)
        bd.extrude(amount=(5.0), mode=bd.Mode.SUBTRACT)

        # --- Aperture cut ---
        # Cut the beam aperture through the center of the holder
        # No offset here — the aperture stays centered regardless of rail offset
        with bd.BuildSketch() as Aperture:
            add_aperture_to_sketch(
                aperture_shape,
                aperture_radius,
                aperture_width,
                aperture_height,
                custom_aperture_points,
            )
        # Subtract the aperture shape from the holder
        bd.extrude(amount=-10, mode=bd.Mode.SUBTRACT)

    logging.info("Cerrobend holder built successfully")
    return CollimatorHolder.part


if __name__ == "__main__":
    from utils import LENGTH_DEFAULT, WIDTH_DEFAULT, THICKNESS_DEFAULT, WALL_DEFAULT, \
        RECTANGLE_WIDTH_DEFAULT, RECTANGLE_HEIGHT_DEFAULT, APERTURE_WIDTH_DEFAULT, APERTURE_HEIGHT_DEFAULT
    import ocp_vscode as ocp

    part = build_cerrobend_holder(
        length=LENGTH_DEFAULT, width=WIDTH_DEFAULT, thickness=THICKNESS_DEFAULT,
        wall=WALL_DEFAULT, rectangle_width=RECTANGLE_WIDTH_DEFAULT,
        rectangle_height=RECTANGLE_HEIGHT_DEFAULT,
        aperture_shape="Rectangular",
        aperture_width=APERTURE_WIDTH_DEFAULT, aperture_height=APERTURE_HEIGHT_DEFAULT,
    )
    ocp.show_all()
