from PyQt6.QtCore import pyqtSlot, pyqtSignal, QThread, QObject
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

class SuggestionGetterX(QObject):
    ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.picks = []
        self.strategic_picks = []
        self.candidates = []
        # self._stop_event = Event()

    def start(self):
        suggestions = self.parent().guess.get_suggestions()
        self.picks, self.strategic_picks, self.candidates = suggestions
        # self.ready.emit()
        # what if we emit the suggestions? think about that

        QThread.currentThread().quit()

        # self.thread = QThread()  # Create a QThread instance
        # self.worker = Worker()    # Create a Worker instance
        # self.worker.moveToThread(self.thread)  # Move Worker to the thread
        
        # # Connect signals
        # self.worker.progress.connect(self.update_progress)
        # self.worker.finished.connect(self.on_finished)
        # self.thread.started.connect(self.worker.do_work)

# class Worker(QObject):
#     finished = pyqtSignal()  # Signal emitted when task is done
#     progress = pyqtSignal(int)  # Optional: for reporting progress
# 
#     @pyqtSlot()
#     def run(self):
#         """Long-running task."""
#         for i in range(5):
#             sleep(1)  # Simulate work
#             self.progress.emit(i + 1)
#         
#         # At the end, denote termination
#         # Option 1: Emit signal (recommended)
#         self.finished.emit()
#         
#         # Option 2: Directly quit the thread (works, but less flexible)
#         # self.thread().quit()  # Or QThread.currentThread().quit()



class DecisionTreeRoutesGetter(QThread):
    ready = pyqtSignal(str, object, bool)

    def __init__(self, profile_manager, pick, guess_manager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.pick = pick
        self.guess_manager = guess_manager
        self.app_cache_path = profile_manager.app_cache_path()
        self.routes = []
        # self._stop_event = Event()

    def run(self):
        try:
            profile_name = self.profile_manager.getCurrentProfileName()
            self.routes = self.guess_manager.gen_routes(self.pick)
            # Verify routes are valid
            if self.routes is None or not self.routes:
                logging.error(f"Invalid or empty routes generated for {self.pick}")
                self.ready.emit(profile_name, None, False)
                return

            # tree = routes_to_dt(self.routes)
            # self.profile_manager.addDecisionTree(profile_name, tree)
            # self.ready.emit(self.pick, True)
            self.ready.emit(profile_name, self.routes, True)
        except Exception as e:
            logging.error(f"Failed to generate decision tree for {self.pick}: {e}")
            self.ready.emit(profile_name, None, False)

    def stop(self):
        self.guess_manager.stop()
