# wordlesmash/__init__.py
"""
WordLeSmash: A PyQt6-based Wordle solver using decision trees.
"""

__version__ = "0.1.0"

# from .main_window import MainWordLeSmashWindow
# from .preferences import MainPreferences
# from .profile_manager import ProfileManager, Profile, GameType
# from .dialogs import ProgressDialog, NewProfileDialog, BatchAddDialog
# from .workers import SuggestionGetter, DecisionTreeRoutesGetter
# from .delegates import UpperCaseValidator, UpperCaseDelegate, MultiBadgeDelegate
# from .ui_loader import load_ui_class, UI_CLASSES

__all__ = [
    "MainWordLeSmashWindow",
    "MainPreferences",
    "ProfileManager",
    "Profile",
    "Models",
    "GameType",
    "ProgressDialog",
    "NewProfileDialog",
    "BatchAddDialog",
    "SuggestionGetter",
    "DecisionTreeRoutesGetter",
    "UpperCaseValidator",
    "UpperCaseDelegate",
    "MultiBadgeDelegate",
    "load_ui_class",
    "UI_CLASSES",
]