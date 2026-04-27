"""Collimator Creator GUI — main entry point.

This file contains only the wxPython GUI, PyVista visualization, and export
dialogs. All CAD build logic lives in the dedicated modules:
    - cerrobend_holder.py  (blue part with rails/stopper)
    - cerrobend_mold.py    (red mold part)
    - degrader.py          (green STL-imported part)

Shared constants and utilities live in utils.py.

Usage:
    python CC_app.py
    # or:
    # 1  conda env create -f environment.yml
    # 2  conda activate cc_env
"""

import logging  # for tracing GUI events
import os  # for os.path.basename in view text
import sys  # for sys.exit on close
import threading  # for running CAD generation off the main thread

import numpy as np
import vtk

import pyvista as pv  # 3D visualization
import wx  # GUI framework

# --- Import the three modular builders ---
from cerrobend_holder import build_cerrobend_holder  # builds the blue holder part
from cerrobend_mold import build_cerrobend_mold  # builds the red mold part
from degrader import build_degrader  # builds the green degrader part

# --- Import shared constants and utilities from utils.py ---
# These were previously defined inline; now centralised so all modules share them
from utils import (
    APERTURE_HEIGHT_DEFAULT,  # default rectangular aperture height (mm)
    APERTURE_RADIUS_DEFAULT,  # default circular aperture radius (mm)
    APERTURE_WIDTH_DEFAULT,  # default rectangular aperture width (mm)
    LENGTH_DEFAULT,  # default holder box length (mm)
    OFFSET_X_DEFAULT,  # default crossline offset (mm)
    OFFSET_Y_DEFAULT,  # default inline offset (mm)
    RECTANGLE_HEIGHT_DEFAULT,  # default tab extrusion height (mm)
    RECTANGLE_WIDTH_DEFAULT,  # default tab extrusion width (mm)
    THICKNESS_DEFAULT,  # default holder box thickness (mm)
    WALL_DEFAULT,  # default holder wall thickness (mm)
    WIDTH_DEFAULT,  # default holder box width (mm)
    export_stl_file,  # STL export helper (raises on failure)
    load_custom_aperture_points,  # JSON polygon point loader (raises on failure)
    view_cad_object,  # build123d part → PyVista PolyData converter
)


class CADViewerApp(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, -1, "Collimator Creator", size=(300, 648))
        panel = wx.Panel(self)

        # Instance variables to hold the generated CAD parts
        self.CollimatorHolder = None
        self.CollimatorMold = None
        self.CollimatorMainHolder = None
        self.plotter = None  # PyVista plotter window reference
        self.current_params = {}

        # STL Import section — for loading an external degrader model
        stl_import_box = wx.StaticBox(panel, label="STL Import")
        stl_import_sizer = wx.StaticBoxSizer(stl_import_box, wx.VERTICAL)

        self.stl_file_path = wx.TextCtrl(panel)
        browse_button = wx.Button(panel, label="Browse")
        browse_button.Bind(wx.EVT_BUTTON, self.on_browse_stl_file)

        stl_import_sizer.Add(self.stl_file_path, 0, wx.ALL | wx.EXPAND, 5)
        stl_import_sizer.Add(browse_button, 0, wx.ALL, 5)

        logging.info("Initializing CAD Viewer App")

        # Template Parameters section — offset controls for rails/stopper
        template_box = wx.StaticBox(panel, label="Template Parameters")
        template_sizer = wx.StaticBoxSizer(template_box, wx.VERTICAL)

        # Commented-out inputs preserved for possible future re-enablement
        # self.length_input = self._create_labeled_input(
        #     panel, template_sizer, "Length:", str(LENGTH_DEFAULT)
        # )
        # self.width_input = self._create_labeled_input(
        #     panel, template_sizer, "Width:", str(WIDTH_DEFAULT)
        # )
        # self.thickness_input = self._create_labeled_input(
        #     panel, template_sizer, "Thickness:", str(THICKNESS_DEFAULT)
        # )
        # self.wall_input = self._create_labeled_input(
        #     panel, template_sizer, "Wall:", str(WALL_DEFAULT)
        # )
        # self.rectangle_width_input = self._create_labeled_input(
        #     panel, template_sizer, "Rectangle Width:", str(RECTANGLE_WIDTH_DEFAULT)
        # )
        # self.rectangle_height_input = self._create_labeled_input(
        #     panel, template_sizer, "Rectangle Length:", str(RECTANGLE_HEIGHT_DEFAULT)
        # )
        self.offset_x_input = self._create_labeled_input(
            panel, template_sizer, "Offset Crossline (X):", str(OFFSET_X_DEFAULT)
        )
        self.offset_y_input = self._create_labeled_input(
            panel, template_sizer, "Offset Inline (Y):", str(OFFSET_Y_DEFAULT)
        )

        # Aperture Parameters section — shape selection and dimension inputs
        aperture_box = wx.StaticBox(panel, label="Aperture Parameters")
        aperture_sizer = wx.StaticBoxSizer(aperture_box, wx.VERTICAL)

        self.aperture_shape = wx.RadioBox(
            panel, label="Aperture Shape", choices=["Rectangular", "Circular", "Custom"]
        )
        self.aperture_shape.Bind(wx.EVT_RADIOBOX, self.on_aperture_shape_changed)
        aperture_sizer.Add(self.aperture_shape, 0, wx.ALL, 5)

        # Custom aperture file picker — only active when "Custom" is selected
        self.custom_aperture_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.custom_aperture_path = wx.TextCtrl(panel)
        self.custom_aperture_browse = wx.Button(panel, label="Browse JSON")
        self.custom_aperture_browse.Bind(wx.EVT_BUTTON, self.on_browse_aperture_json)
        self.custom_aperture_sizer.Add(
            self.custom_aperture_path, 1, wx.EXPAND | wx.RIGHT, 5
        )
        self.custom_aperture_sizer.Add(self.custom_aperture_browse, 0)
        aperture_sizer.Add(self.custom_aperture_sizer, 0, wx.ALL | wx.EXPAND, 5)

        self.rectangular_aperture_width_input = self._create_labeled_input(
            panel,
            aperture_sizer,
            "Aperture Crossline (X):",
            str(APERTURE_WIDTH_DEFAULT),
        )
        self.rectangular_aperture_height_input = self._create_labeled_input(
            panel, aperture_sizer, "Aperture Inline (Y):", str(APERTURE_HEIGHT_DEFAULT)
        )
        self.circular_aperture_input = self._create_labeled_input(
            panel, aperture_sizer, "Aperture Radius:", str(APERTURE_RADIUS_DEFAULT)
        )

        # Initially disable inputs that don't match the default selection
        self._update_aperture_inputs_for_shape("Rectangular")

        # Functions section — generate, export, and close buttons
        function_box = wx.StaticBox(panel, label="Functions")
        function_sizer = wx.StaticBoxSizer(function_box, wx.VERTICAL)

        self.generate_button = wx.Button(panel, label="Generate and View")
        self.generate_button.Bind(wx.EVT_BUTTON, self.on_generate_and_view)
        function_sizer.Add(self.generate_button, 0, wx.ALL, 5)

        export_button = wx.Button(panel, label="Export STL")
        export_button.Bind(wx.EVT_BUTTON, self.on_export_stl_files)
        function_sizer.Add(export_button, 0, wx.ALL, 5)

        close_button = wx.Button(panel, label="Close All and Exit")
        close_button.Bind(wx.EVT_BUTTON, self.on_close_and_exit)
        function_sizer.Add(close_button, 0, wx.ALL, 5)

        # Assemble the main layout
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(template_sizer, 0, wx.ALL | wx.EXPAND, 10)
        main_sizer.Add(aperture_sizer, 0, wx.ALL | wx.EXPAND, 10)
        main_sizer.Add(stl_import_sizer, 0, wx.ALL | wx.EXPAND, 10)
        main_sizer.Add(function_sizer, 0, wx.ALL | wx.EXPAND, 10)

        panel.SetSizer(main_sizer)

        # Remove any minimum size constraints so the sizer can determine size
        self.SetMinSize(wx.DefaultSize)
        panel.SetMinSize(wx.DefaultSize)

        # Fit the sizer to the panel and lock the minimum window size
        panel.Fit()
        self.SetMinSize(panel.GetSize())

        # Bind the size event to enforce minimum size
        self.Bind(wx.EVT_SIZE, self.on_enforce_min_size)

        self.Centre()

    def _create_labeled_input(self, parent, sizer, label, default):
        """Create a labeled input field with mm units, right-aligned in its row."""
        hsizer = wx.BoxSizer(wx.HORIZONTAL)
        static_text = wx.StaticText(parent, label=label)
        input_field = wx.TextCtrl(
            parent, value=default, size=(60, -1), style=wx.TE_RIGHT
        )
        unit_label = wx.StaticText(parent, label="mm")

        hsizer.Add(static_text, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hsizer.Add((0, 0), 1, wx.EXPAND)  # spacer pushes input field to the right
        hsizer.Add(input_field, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hsizer.Add(unit_label, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(hsizer, 0, wx.ALL | wx.EXPAND, 5)
        return input_field

    def on_enforce_min_size(self, event):
        """Enforce minimum window size on resize."""
        current_size = self.GetSize()
        min_size = self.GetMinSize()

        new_width = max(current_size.width, min_size.width)
        new_height = max(current_size.height, min_size.height)

        if new_width != current_size.width or new_height != current_size.height:
            self.SetSize(new_width, new_height)
        else:
            event.Skip()

    def on_browse_stl_file(self, event):
        """Open file dialog for STL import."""
        with wx.FileDialog(
            self,
            "Open STL file",
            wildcard="STL files (*.stl)|*.stl",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = fileDialog.GetPath()
            self.stl_file_path.SetValue(pathname)

    def on_aperture_shape_changed(self, event):
        """Enable/disable inputs when the aperture shape radio changes."""
        selected_shape = self.aperture_shape.GetStringSelection()
        self._update_aperture_inputs_for_shape(selected_shape)

    def _update_aperture_inputs_for_shape(self, shape):
        """Enable only the input fields relevant to the selected aperture shape."""
        if shape == "Rectangular":
            self.circular_aperture_input.Disable()
            self.rectangular_aperture_width_input.Enable()
            self.rectangular_aperture_height_input.Enable()
            self.custom_aperture_path.Disable()
            self.custom_aperture_browse.Disable()
        elif shape == "Circular":
            self.circular_aperture_input.Enable()
            self.rectangular_aperture_width_input.Disable()
            self.rectangular_aperture_height_input.Disable()
            self.custom_aperture_path.Disable()
            self.custom_aperture_browse.Disable()
        else:  # Custom
            self.circular_aperture_input.Disable()
            self.rectangular_aperture_width_input.Disable()
            self.rectangular_aperture_height_input.Disable()
            self.custom_aperture_path.Enable()
            self.custom_aperture_browse.Enable()

    def on_generate_and_view(self, event):
        """Read GUI inputs and launch CAD generation on a background thread."""
        # Clear previous objects so stale parts don't linger
        self.CollimatorHolder = None
        self.CollimatorMold = None
        self.CollimatorMainHolder = None

        # Close the previous plotter if it exists
        self.close_viewer()

        try:
            # Use default values for the commented-out inputs
            length = LENGTH_DEFAULT
            width = WIDTH_DEFAULT
            thickness = THICKNESS_DEFAULT
            wall = WALL_DEFAULT
            rectangle_width = RECTANGLE_WIDTH_DEFAULT
            rectangle_height = RECTANGLE_HEIGHT_DEFAULT

            # Read active inputs from the GUI (must happen on the main thread)
            aperture_shape = self.aperture_shape.GetStringSelection()
            offset_x = float(self.offset_x_input.GetValue())
            offset_y = float(self.offset_y_input.GetValue())
            stl_file_path = self.stl_file_path.GetValue()

            # Determine aperture dimensions based on the selected shape
            if aperture_shape == "Circular":
                aperture_radius = float(self.circular_aperture_input.GetValue())
                aperture_width = 2 * aperture_radius
                aperture_height = 2 * aperture_radius
            elif aperture_shape == "Rectangular":
                aperture_width = float(self.rectangular_aperture_width_input.GetValue())
                aperture_height = float(
                    self.rectangular_aperture_height_input.GetValue()
                )
                aperture_radius = None
            else:  # Custom
                # Dimensions unused for custom shapes, but set defaults for logging
                aperture_width = APERTURE_WIDTH_DEFAULT
                aperture_height = APERTURE_HEIGHT_DEFAULT
                aperture_radius = None

            # Pre-load custom aperture points on the main thread (thread safety:
            # self.custom_aperture_path.GetValue() is a wx call that must run here)
            custom_aperture_points = None
            if aperture_shape == "Custom":
                json_path = self.custom_aperture_path.GetValue()
                custom_aperture_points = load_custom_aperture_points(json_path)

            logging.info(
                f"Generating CAD objects with parameters: length={length}, width={width}, "
                f"thickness={thickness}, wall={wall}, rectangle_width={rectangle_width}, "
                f"rectangle_height={rectangle_height}, aperture_shape={aperture_shape}, "
                f"aperture_radius={aperture_radius}, aperture_width={aperture_width}, "
                f"aperture_height={aperture_height}, offset_x={offset_x}, offset_y={offset_y}, "
                f"stl_file_path={stl_file_path}"
            )

            # Generate CAD objects in a separate thread to keep the GUI responsive
            thread = threading.Thread(
                target=self._build_all_parts_thread,
                args=(
                    length,
                    width,
                    thickness,
                    wall,
                    rectangle_width,
                    rectangle_height,
                    aperture_shape,
                    aperture_radius,
                    aperture_width,
                    aperture_height,
                    offset_x,
                    offset_y,
                    stl_file_path,
                    custom_aperture_points,
                ),
            )
            thread.start()

        except ValueError as e:
            logging.error(f"Invalid input: {str(e)}")
            wx.MessageBox(
                f"Please enter valid numeric values for all fields.\n{str(e)}",
                "Error",
                wx.OK | wx.ICON_ERROR,
            )

    def on_close_and_exit(self, event):
        """Close the viewer and exit the application."""
        logging.info("Closing application")
        self.close_viewer()
        self.Close()
        sys.exit(0)

    def close_viewer(self):
        """Safely close the PyVista viewer if one is open."""
        if hasattr(self, "plotter") and self.plotter is not None:
            try:
                self.plotter.close()
                logging.info("Plotter closed")
            except Exception as e:
                logging.error(f"Error closing plotter: {str(e)}")
            self.plotter = None

    def _build_all_parts_thread(self, *args):
        """Thread wrapper: calls _build_all_parts and schedules visualization."""
        try:
            results = self._build_all_parts(*args)
            if results and len(results) == 3:
                (
                    self.CollimatorHolder,
                    self.CollimatorMold,
                    self.CollimatorMainHolder,
                ) = results
                logging.info("CAD objects generated successfully")
                # Schedule visualization on the main thread (wx requires it)
                wx.CallAfter(self.show_parts_in_viewer)
            else:
                raise ValueError("Unexpected number of objects generated")
        except Exception as e:
            logging.error(f"Error generating CAD objects: {str(e)}")
            wx.CallAfter(
                wx.MessageBox,
                f"Error generating CAD objects: {str(e)}",
                "Error",
                wx.OK | wx.ICON_ERROR,
            )

    def _build_all_parts(
        self,
        length,
        width,
        thickness,
        wall,
        rectangle_width,
        rectangle_height,
        aperture_shape,
        aperture_radius,
        aperture_width,
        aperture_height,
        offset_x,
        offset_y,
        stl_file_path,
        custom_aperture_points,
    ):
        """Delegate CAD generation to the three builder modules.

        Each builder is an independent module that can also be imported and
        used directly in custom scripts without the GUI.
        """
        # Build the cerrobend holder (blue part with rails, stopper, tabs)
        # offset_x/offset_y only affect this part's rails and stopper
        holder_part = build_cerrobend_holder(
            length=length,
            width=width,
            thickness=thickness,
            wall=wall,
            rectangle_width=rectangle_width,
            rectangle_height=rectangle_height,
            aperture_shape=aperture_shape,
            aperture_radius=aperture_radius,
            aperture_width=aperture_width,
            aperture_height=aperture_height,
            offset_x=offset_x,
            offset_y=offset_y,
            custom_aperture_points=custom_aperture_points,
        )

        # Build the cerrobend mold (red part — no offsets needed)
        mold_part = build_cerrobend_mold(
            length=length,
            width=width,
            thickness=thickness,
            aperture_shape=aperture_shape,
            aperture_radius=aperture_radius,
            aperture_width=aperture_width,
            aperture_height=aperture_height,
            custom_aperture_points=custom_aperture_points,
        )

        # Build the degrader (green part — STL import + aperture cut)
        degrader_part = build_degrader(
            stl_file_path=stl_file_path,
            aperture_shape=aperture_shape,
            aperture_radius=aperture_radius,
            aperture_width=aperture_width,
            aperture_height=aperture_height,
            custom_aperture_points=custom_aperture_points,
        )

        return holder_part, mold_part, degrader_part

    def show_parts_in_viewer(self):
        """Create a 3-panel PyVista viewer showing all generated parts."""
        aperture_shape = self.aperture_shape.GetStringSelection()
        try:
            logging.info("Attempting to view CAD objects")

            # Build the info text overlay based on aperture shape
            if aperture_shape == "Custom":
                txt = "Aperture Shape: Custom\nUsing points from: " + os.path.basename(
                    self.custom_aperture_path.GetValue()
                )
            else:
                aperture_width = float(self.rectangular_aperture_width_input.GetValue())
                aperture_height = float(
                    self.rectangular_aperture_height_input.GetValue()
                )
                txt = (
                    "Aperture Shape: "
                    + str(aperture_shape)
                    + "\n"
                    + "Aperture Crossline: "
                    + str(aperture_width)
                    + "\n"
                    + "Aperture Inline: "
                    + str(aperture_height)
                )

            # Create a 1×3 subplot plotter (one panel per part)
            self.plotter = pv.Plotter(shape=(1, 3), title="Collimator Viewer")
            # Hide all three default border rectangles
            for idx in (0, 1, 2):
                actor = self.plotter.renderers[idx]._border_actor
                if actor is not None:
                    actor.VisibilityOff()
            # Add vertical-only separator lines on the middle renderer
            points = np.array(
                [[1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]
            )
            sep_poly = pv.PolyData()
            sep_poly.points = points
            sep_poly.lines = np.hstack([[2, 1, 2], [2, 3, 0]])  # left and right only
            sep_mapper = vtk.vtkPolyDataMapper2D()
            sep_mapper.SetInputData(sep_poly)
            sep_coord = vtk.vtkCoordinate()
            sep_coord.SetCoordinateSystemToNormalizedViewport()
            sep_mapper.SetTransformCoordinate(sep_coord)
            sep_actor = vtk.vtkActor2D()
            sep_actor.SetMapper(sep_mapper)
            sep_actor.GetProperty().SetColor(0, 0, 0)
            sep_actor.GetProperty().SetLineWidth(2.0)
            self.plotter.renderers[1].AddActor(sep_actor)

            # --- Panel 0: Cerrobend Holder (blue) ---
            if self.CollimatorHolder:
                # Convert build123d part to PyVista mesh via utils helper
                holder_mesh = view_cad_object(self.CollimatorHolder)
                holder_mesh.compute_normals(inplace=True)
                self.plotter.subplot(0, 0)
                self.plotter.show_axes()
                self.plotter.add_mesh(
                    holder_mesh, color="blue", show_edges=False, smooth_shading=True
                )
                self.plotter.add_text(
                    text=str(txt), position="upper_right", font_size=8
                )
                self.plotter.add_text(
                    "Mountable \nCerrobend Shell", position="upper_left", font_size=12
                )

            # --- Panel 1: Cerrobend Mold (red) ---
            if self.CollimatorMold:
                mold_mesh = view_cad_object(self.CollimatorMold)
                mold_mesh.compute_normals(inplace=True)
                self.plotter.subplot(0, 1)
                self.plotter.show_axes()
                self.plotter.add_mesh(
                    mold_mesh, color="red", show_edges=False, smooth_shading=True
                )
                self.plotter.add_text(
                    "Cerrobend Mold", position="upper_left", font_size=12
                )

            # --- Panel 2: Collimator Degrader (green) ---
            if self.CollimatorMainHolder:
                main_holder_mesh = view_cad_object(self.CollimatorMainHolder)
                main_holder_mesh.compute_normals(inplace=True)
                self.plotter.subplot(0, 2)
                self.plotter.show_axes()
                self.plotter.add_mesh(
                    main_holder_mesh,
                    color="green",
                    show_edges=False,
                    smooth_shading=True,
                )
                self.plotter.add_text(
                    "Collimator Degrader", position="upper_left", font_size=12
                )

            # Position the plotter window relative to the main GUI window
            main_window_pos = self.GetPosition()
            main_window_size = self.GetSize()
            display = wx.Display().GetGeometry()
            screen_width = display.GetWidth()
            screen_height = display.GetHeight()

            # Size plotter to 80% of screen width and 40% of screen height
            plotter_width = int(screen_width * 0.8)
            plotter_height = int(screen_height * 0.4)

            # Place plotter to the right of the main window, vertically centered
            plotter_x = (
                main_window_pos.x + (main_window_size.width + plotter_width) // 2
            )
            plotter_y = (
                main_window_pos.y + (main_window_size.height - plotter_height) // 2
            )

            self.plotter.render_window.SetPosition([plotter_x, plotter_y])
            self.plotter.render_window.SetSize([plotter_width, plotter_height])

            # Show the plotter (non-blocking so the GUI stays responsive)
            self.plotter.show(auto_close=False)

            logging.info("CAD objects viewed successfully")

        except Exception as e:
            logging.error(f"Error viewing CAD objects: {str(e)}")
            wx.MessageBox(
                f"Error viewing CAD objects: {str(e)}", "Error", wx.OK | wx.ICON_ERROR
            )

    def on_export_stl_files(self, event):
        """Export all three generated parts to STL files via sequential dialogs."""
        if (
            not self.CollimatorHolder
            or not self.CollimatorMold
            or not self.CollimatorMainHolder
        ):
            logging.warning("Attempted to export STL without generating CAD objects")
            wx.MessageBox(
                "Please generate the CAD objects first.", "Error", wx.OK | wx.ICON_ERROR
            )
            return

        # Export degrader (Collimator Main Holder)
        with wx.FileDialog(
            self,
            "Save Collimator Main Holder STL file",
            wildcard="STL files (*.stl)|*.stl",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            main_holder_filename = fileDialog.GetPath()
            try:
                export_stl_file(self.CollimatorMainHolder, main_holder_filename)
            except Exception as e:
                wx.MessageBox(
                    f"Error exporting STL file: {str(e)}",
                    "Error",
                    wx.OK | wx.ICON_ERROR,
                )
                return

        # Export cerrobend holder
        with wx.FileDialog(
            self,
            "Save Collimator Holder STL file",
            wildcard="STL files (*.stl)|*.stl",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            holder_filename = fileDialog.GetPath()
            try:
                export_stl_file(self.CollimatorHolder, holder_filename)
            except Exception as e:
                wx.MessageBox(
                    f"Error exporting STL file: {str(e)}",
                    "Error",
                    wx.OK | wx.ICON_ERROR,
                )
                return

        # Export cerrobend mold
        with wx.FileDialog(
            self,
            "Save Collimator Mold STL file",
            wildcard="STL files (*.stl)|*.stl",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            mold_filename = fileDialog.GetPath()
            try:
                export_stl_file(self.CollimatorMold, mold_filename)
            except Exception as e:
                wx.MessageBox(
                    f"Error exporting STL file: {str(e)}",
                    "Error",
                    wx.OK | wx.ICON_ERROR,
                )
                return

        logging.info(f"STL files exported: {holder_filename}, {mold_filename}")
        wx.MessageBox(
            "STL files saved successfully!", "Success", wx.OK | wx.ICON_INFORMATION
        )

    def on_browse_aperture_json(self, event):
        """Open file dialog for selecting a custom aperture JSON file."""
        # Use wx.FD_DEFAULT_STYLE to suppress macOS deprecation warnings
        dialog = wx.FileDialog(
            self,
            "Open Custom Aperture JSON file",
            wildcard="JSON files (*.json)|*.json",
            style=wx.FD_DEFAULT_STYLE | wx.FD_FILE_MUST_EXIST,
        )

        try:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = dialog.GetPath()
            self.custom_aperture_path.SetValue(pathname)
        finally:
            dialog.Destroy()


def main():
    app = wx.App()
    frame = CADViewerApp()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
