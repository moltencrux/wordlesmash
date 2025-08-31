import logging
# import sys
from importlib.resources import files
from pathlib import Path
from PyQt6 import uic

def pathhelper(resource, package='wordlesmash.ui'):
    """Helper to resolve resource paths."""
    return Path(files(package) / resource)

def load_ui_class(ui_filename, ui_class_name):
    """
    Load a UI class dynamically based on whether the .ui file is newer than the generated .py.
    
    Args:
        ui_filename (str): Name of the .ui file (e.g., 'WordLeSmash.ui')
        ui_class_name (str): Name of the UI class (e.g., 'Ui_MainWindow')
    
    Returns:
        type: The UI class (either from uic.loadUiType or imported module)
    """
    ui_path = pathhelper(ui_filename)
    ui_py_path = pathhelper(f"{ui_filename.rsplit('.', 1)[0]}_ui.py")
    
    # Check if .ui is newer than .py
    try:
        ui_mtime = ui_path.stat().st_mtime
        py_mtime = ui_py_path.stat().st_mtime if ui_py_path.exists() else 0
        is_ui_newer = ui_mtime > py_mtime
    except FileNotFoundError:
        is_ui_newer = True  # If .py doesn't exist, use .ui
        logging.debug(f"No generated .py file found for {ui_filename}, loading .ui directly")
    
    if is_ui_newer:
        logging.debug(f"Loading UI file directly: {ui_filename}")
        return uic.loadUiType(ui_path)[0]
    else:
        logging.debug(f"Loading generated file: {ui_py_path}")
        module = __import__(f"wordlesmash.ui.{ui_py_path.stem}", fromlist=[ui_class_name])
        return getattr(module, ui_class_name)

# Define UI mappings for convenience
UI_CLASSES = {
    'MainWordLeSmashWindow': ('WordLeSmash.ui', 'Ui_MainWindow'),
    'MainPreferences': ('preferences.ui', 'Ui_preferences'),
    'ProgressDialog': ('ProgressDialog.ui', 'Ui_ProgressDialog'),
    'NewProfileDialog': ('NewProfile.ui', 'Ui_NewProfile'),
    'BatchAddDialog': ('BatchAdd.ui', 'Ui_BatchAdd'),
}
