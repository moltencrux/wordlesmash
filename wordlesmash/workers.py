from PyQt6.QtCore import pyqtSlot, pyqtSignal, QThread
from threading import Event
from pathlib import Path
from .tree_utils import routes_to_text, routes_to_dt
import logging

class SuggestionGetter(QThread):
    ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.picks = []
        self.strategic_picks = []
        self.candidates = []
        # self._stop_event = Event()

    def run(self):
        suggestions = self.parent().guess.get_suggestions()
        self.picks, self.strategic_picks, self.candidates = suggestions
        self.ready.emit()


class DecisionTreeRoutesGetter(QThread):
    ready = pyqtSignal(str, bool)

    def __init__(self, profile_manager, pick, guess_manager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.pick = pick
        self.guess_manager = guess_manager
        self.app_cache_path = profile_manager.app_cache_path()
        self.routes = []
        self._stop_event = Event()

    def run(self):
        try:
            self.routes = self.guess_manager.gen_routes(self.pick)
            # Verify routes are valid
            if self.routes is None or not self.routes:
                logging.error(f"Invalid or empty routes generated for {self.pick}")
                self.ready.emit(self.pick, False)
                return

            tree = routes_to_dt(self.routes)
            profile_name = self.profile_manager.getCurrentProfile()
            self.profile_manager.addDecisionTree(profile_name, tree)
            self.ready.emit(self.pick, True)
        except Exception as e:
            logging.error(f"Failed to generate decision tree for {self.pick}: {e}")
            self.ready.emit(self.pick, False)

    def stop(self):
        self.guess_manager.stop()
