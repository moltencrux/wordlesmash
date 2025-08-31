#!/usr/bin/env -S python3 -O
import logging, sys, os
from PyQt6.QtCore import (QCoreApplication, QSettings, QStandardPaths, Qt,
    pyqtSlot, pyqtSignal, QObject, QThread, QModelIndex, QEvent, QTimer, QSize,
    QRect
)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QDialog, QListWidgetItem,
    QMessageBox, QItemDelegate, QLineEdit, QListWidget, QFormLayout, QSpinBox,
    QDialogButtonBox, QComboBox, QTreeWidgetItem, QStyledItemDelegate
)
from PyQt6.QtGui import (QColorConstants, QValidator, QFont, QTextCursor,
    QCloseEvent, QIcon, QPainter, QColor
)

from threading import Event
from importlib.resources import files
from pathlib import Path
from utils import all_files_newer
from solver import GuessManager, Color, DecisionTreeGuessManager
import shutil
import tempfile
import re
from tree_utils import routes_to_text, routes_to_dt, read_decision_routes, dt_to_text
from itertools import cycle
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
QCoreApplication.setApplicationName('WordLeSmash')
QCoreApplication.setOrganizationName('moltencrux')
if __debug__:
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    logging.debug('debug mode on')
else:
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR)

def pathhelper(resource, package='ui'):
    return Path(files(package) / resource)

wordlesmash_ui_path = pathhelper('WordLeSmash.ui')
preferences_ui_path = pathhelper('preferences.ui')
newprofile_ui_path = pathhelper('NewProfile.ui')
batchadd_ui_path = pathhelper('BatchAdd.ui')
progressdialog_ui_path = pathhelper('ProgressDialog.ui')

wordlesmash_ui_py_path = pathhelper('WordLeSmash_ui.py')
preferences_ui_py_path = pathhelper('preferences_ui.py')
newprofile_ui_py_path = pathhelper('NewProfile_ui.py')
batchadd_ui_py_path = pathhelper('BatchAdd_ui.py')
progressdialog_ui_py_path = pathhelper('ProgressDialog_ui.py')

wordlesmash_rc_py_path = pathhelper('wordlesmash_rc.py')

from ui.wordlesmash_rc import qInitResources
qInitResources()

ui_paths = [wordlesmash_ui_path, preferences_ui_path, newprofile_ui_path,
            batchadd_ui_path, progressdialog_ui_path]

ui_py_paths = [wordlesmash_ui_py_path, preferences_ui_py_path,
               newprofile_ui_py_path, batchadd_ui_py_path, progressdialog_ui_py_path]

# if ANY .ui file is newer than any generated .py file, prefer compiling the UI.
match all_files_newer(ui_paths, ui_py_paths):

    case True:
        logging.debug('importing ui files')
        from PyQt6 import uic
        Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path)
        Ui_preferences, _ = uic.loadUiType(preferences_ui_path)
        Ui_NewProfile, _ = uic.loadUiType(newprofile_ui_path)
        Ui_BatchAdd, _ = uic.loadUiType(batchadd_ui_path)
        Ui_ProgressDialog, _ = uic.loadUiType(progressdialog_ui_path)
    case False:
        logging.debug('importing generated files')
        from ui.WordLeSmash_ui import Ui_MainWindow
        from ui.preferences_ui import Ui_preferences
        from ui.NewProfile_ui import Ui_NewProfile
        from ui.BatchAdd_ui import Ui_BatchAdd
        from ui.ProgressDialog_ui import Ui_ProgressDialog
    case _:
        logging.critical('UI imports unavailable, exiting...')
        sys.exit(-1)

class GameType(Enum):
    WORDLE = "wordle"
    NYT_NORMAL = "NYT - Normal Mode"
    OTHER = "other"

@dataclass
class Profile:
    word_length: int = 5
    dt: Dict[str, str] = field(default_factory=dict)  # {pick: path to dtree/<pick>.txt}
    game_type: GameType = GameType.WORDLE
    candidates: List[str] = field(default_factory=list)
    picks: List[str] = field(default_factory=list)
    initial_picks: List[str] = field(default_factory=list)  # {pick: status}
    original_name: Optional[str] = None
    dirty: bool = False

class ProfileManager:
    def __init__(self, parent=None, settings=None):
        self.settings = settings if settings is not None else QSettings()
        self.app_data_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self._app_cache_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
        self.modified: Dict[str, Profile] = {}
        self.loaded: Dict[str, Profile] = {}
        self.to_delete: List[str] = []  # Track profiles to delete on OK/Apply
        self._default_profile = self.settings.value("default_profile", defaultValue=None)
        self.current_profile = self.getDefaultProfile()

    def getCurrentProfile(self) -> Optional[str]:
        return self.current_profile

    def setCurrentProfile(self, name: str):
        self.current_profile = name
        logging.debug(f"Set current profile: {name}")

    def getDefaultProfile(self) -> Optional[str]:
        return self._default_profile

    def setDefaultProfile(self, name: str):
        self._default_profile = name

    def getProfileNames(self) -> List[str]:
        self.settings.beginGroup("profiles")
        names = self.settings.childGroups()
        self.settings.endGroup()
        return names

    def getPicks(self) -> List[str]:
        profile = self.loadProfile(self.current_profile)
        return profile.picks

    def getCandidates(self) -> List[str]:
        profile = self.loadProfile(self.current_profile)
        return profile.candidates

    def getDecisionTrees(self):
        profile = self.getCurrentProfile()
        profile_dir = Path(self.app_data_path) / "profiles" / profile
        dtree_dir = profile_dir / "dtree"
        return tuple(dtree_dir.glob("*.txt"))

    def getWordLength(self) -> int:
        profile = self.loadProfile(self.current_profile)
        return profile.word_length

    def app_cache_path(self) -> str:
        return str(self._app_cache_path)

    def loadProfile(self, name: str) -> Profile:
        if name in self.modified:
            logging.debug(f"Loading modified profile: {name}, picks: {self.modified[name].picks}, candidates: {self.modified[name].candidates}")
            return self.modified[name]
        if name in self.loaded:
            return self.loaded[name]
        profile = Profile()
        self.settings.beginGroup(f"profiles/{name}")
        profile.word_length = int(self.settings.value("word_length", 5))
        profile.game_type = GameType(self.settings.value("game_type", GameType.WORDLE.value))
        # Handle initial_picks as list or dict (for backward compatibility)
        initial_picks = self.settings.value("initial_picks", [], type=list)
        if isinstance(initial_picks, dict):
            profile.initial_picks = list(initial_picks.keys())  # Convert dict to list
        else:
            profile.initial_picks = [pick for pick in initial_picks if pick]
        profile.dt = {}
        profile_dir = self.app_data_path / "profiles" / name
        # Load picks from picks.txt
        picks_file = profile_dir / "picks.txt"
        profile.picks = []
        if picks_file.exists():
            with picks_file.open("r", encoding="utf-8") as f:
                profile.picks = [line.strip().upper() for line in f if line.strip()]
        # Load candidates from candidates.txt
        candidates_file = profile_dir / "candidates.txt"
        profile.candidates = []
        if candidates_file.exists():
            with candidates_file.open("r", encoding="utf-8") as f:
                profile.candidates = [line.strip().upper() for line in f if line.strip()]
        # Load decision trees
        if profile_dir.exists():
            dtree_dir = profile_dir / "dtree"
            if dtree_dir.exists():
                dt_files = dtree_dir.glob("*.txt")
                profile.dt = routes_to_dt(route for file in dt_files for route in
                    read_decision_routes(file)
                )
        self.settings.endGroup()
        self.loaded[name] = profile
        return profile

    def saveProfile(self, name: str, profile: Profile):
        self.settings.beginGroup(f"profiles/{name}")
        self.settings.setValue("word_length", profile.word_length)
        self.settings.setValue("game_type", profile.game_type.value)
        self.settings.setValue("initial_picks", profile.initial_picks)  # Save as list
        self.settings.endGroup()
        self.settings.sync()
        profile_dir = self.app_data_path / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        # Save picks to picks.txt
        with open(profile_dir / "picks.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(profile.picks))
        # Save candidates to candidates.txt
        with open(profile_dir / "candidates.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(profile.candidates))
        logging.debug(f"Saved profile: {name}, initial_picks: {profile.initial_picks}, picks: {profile.picks}, candidates: {profile.candidates}")
        dtree_dir = profile_dir / "dtree"
        dtree_dir.mkdir(parents=True, exist_ok=True)
        for word, subtree in profile.dt.items():
            with open(dtree_dir / f"{word}.txt", "w", encoding="utf-8") as f:
                f.write(dt_to_text({word: subtree}))

    def deleteProfile(self, name: str):
        # Mark profile for deletion instead of immediate removal
        if name not in self.to_delete:
            self.to_delete.append(name)
            logging.debug(f"Marked profile {name} for deletion")
        if name == self.current_profile:
            self.current_profile = None
        if name == self._default_profile:
            self._default_profile = None
            logging.debug(f"Deleted default profile {name}, _default_profile set to None")

    def processDeletions(self):
        # Process all marked deletions
        for name in self.to_delete:
            logging.debug(f"Processing deletion for profile {name}")
            self.settings.beginGroup("profiles")
            self.settings.remove(name)
            self.settings.endGroup()
            self.settings.sync()
            profile_dir = self.app_data_path / "profiles" / name
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
            if name in self.modified:
                del self.modified[name]
            if name in self.loaded:
                del self.loaded[name]
        self.to_delete.clear()
        logging.debug("All marked profiles deleted")

    def modifyProfile(self, name: str, original_name: Optional[str] = None) -> Profile:
        logging.debug(f"modifyProfile called for name: {name}, original_name: {original_name}")
        if name in self.modified:
            profile = self.modified[name]
            logging.debug(f"Returning existing modified profile: {name}")
        else:
            if name in self.loaded:
                profile = self.loaded.pop(name)
                logging.debug(f"Popped profile from loaded: {name}")
            else:
                profile = self.loadProfile(name) if original_name else Profile()
                logging.debug(f"Created new profile for: {name}")
            profile.original_name = original_name if original_name else name
            profile.dirty = True
            self.modified[name] = profile
        # Update _default_profile if renaming the default profile
        if original_name and original_name == self._default_profile:
            self._default_profile = name
            logging.debug(f"Default profile renamed from {original_name} to {name}")
        return profile

    def has_pending_changes(self) -> bool:
        """Check if there are any pending changes to profiles or default profile."""
        current_default = self.settings.value("default_profile", defaultValue=None)
        default_changed = self._default_profile != current_default
        return bool(self.modified or self.to_delete or default_changed)

    def commitChanges(self):
        """Save all modified profiles, process deletions, and update default profile."""
        logging.debug("Committing changes in ProfileManager")
        self.processDeletions()  # Process pending deletions
        for name, profile in self.modified.items():
            if profile.dirty:
                logging.debug(f"Saving profile: {name}, initial_picks: {profile.initial_picks}, picks: {profile.picks}, candidates: {profile.candidates}")
                self.saveProfile(name, profile)
        # Save default profile if changed
        current_default = self.settings.value("default_profile", defaultValue=None)
        if self._default_profile != current_default:
            # Validate that _default_profile exists
            valid_profiles = self.getProfileNames() + list(self.modified.keys())
            if self._default_profile is None or self._default_profile in valid_profiles:
                self.settings.setValue("default_profile", self._default_profile)
                self.settings.sync()
                logging.debug(f"Saved default profile to QSettings: {self._default_profile}")
            else:
                logging.warning(f"Invalid default profile {self._default_profile}, not saving to QSettings")
        self.modified.clear()
        logging.debug("All changes committed, cleared modified profiles")


class ProgressDialog(QDialog, Ui_ProgressDialog):
    def __init__(self, parent=None, cancel_callback=None):
        super().__init__(parent)
        self.cancel_callback = cancel_callback
        self.initUI()
        self.last_periods = cycle('<tt>' + s.replace(' ', '&nbsp;') + "</tt>"
            for s in ['   ', '.  ', '.. ', '...']
        )
        self.timer = QTimer(self)  # Initialize QTimer
        self.timer.timeout.connect(self.updateLabel)  # Connect timeout signal to updateLabel method
        self.timer.start(400)  # Start the timer with a 500 ms interval
        logging.debug("ProgressDialog initialized, timer started")

    def initUI(self):
        self.setupUi(self)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoTitleBarBackgroundHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        logging.debug(f"ProgressDialog window flags: {self.windowFlags()}")
        try:
            self.spinner.start()
            logging.debug("ProgressDialog spinner started")
        except AttributeError as e:
            logging.error(f"ProgressDialog spinner not properly initialized: {e}")
        self.cancelButton.clicked.connect(self.onCancelRequested)

    def updateLabel(self):
        # Update the label text with the current period
        base_text, *_ = self.label.text().split('<tt>')
        self.label.setText(base_text + next(self.last_periods))

    def onCancelRequested(self):
        self.spinner.setDisabled(True)
        self.label.setText("Canceling routes generation")
        logging.debug("Cancellation requested in ProgressDialog")
        if self.cancel_callback:
            try:
                self.cancel_callback()
                logging.debug("Called cancel_callback in ProgressDialog")
            except Exception as e:
                logging.error(f"Error executing cancel_callback: {e}")

    def keyPressEvent(self, event):
        logging.debug(f"ProgressDialog keyPressEvent: key={event.key()}, focusWidget={self.focusWidget()}, flags={self.windowFlags()}")
        if event.key() == Qt.Key.Key_Escape:
            logging.debug("Esc key press in ProgressDialog, triggering onCancelRequested")
            self.onCancelRequested()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent):
        """Stop the timer and spinner before closing the dialog."""
        logging.debug("ProgressDialog closeEvent triggered")
        self.timer.stop()
        logging.debug("ProgressDialog timer stopped")
        try:
            self.spinner.stop()
            logging.debug("ProgressDialog spinner stopped")
        except AttributeError as e:
            logging.error(f"ProgressDialog spinner not properly initialized: {e}")
        logging.debug("ProgressDialog cancelButton signal disconnected")
        super().closeEvent(event)


class MainWordLeSmashWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setupUi(self)
        self.settings = QSettings()
        self.profile_manager = ProfileManager(self, self.settings)
        self.guessDisplay.setFocus()
        self.resetGuessManager()
        self.onWordSubmitted()
        self.guessDisplay.wordSubmitted.connect(self.onWordSubmitted)
        self.guessDisplay.wordWithdrawn.connect(self.onWordWithdrawn)
        self.resetButton.clicked.connect(self.onResetGame)


        #self.key_ENTER.setStyleSheet("background-color: red; color: white; :disabled {background-color: gray; color: black;} :enabled {background-color: green; color: white;}")
        # self.key_ENTER.setStyleSheet(":disabled {background-color: gray; color: darkgray;} :enabled {background-color: green; color: white;}")

        # self.key_A.setStyleSheet("""
        #     QPushButton {
        #         background-color: #ffa500;
        #         border: 5px solid #15cb1b;
        #         border-style: solid;
        #         border-radius: 5px
        #     }
        # """)
        
        self.guessDisplay.set_color_callback(self.guess.get_allowed_colors_by_slot)

        self.preferences_ui = MainPreferences(self)
        self.actionPreferences.triggered.connect(self.preferences_ui.show)

    def resetGuessManager(self):
        self.guess = DecisionTreeGuessManager(
            self.profile_manager.getPicks(),
            self.profile_manager.getCandidates(),
            self.profile_manager.getDecisionTrees(),
            length=self.profile_manager.getWordLength(),
            cache_path=self.profile_manager.app_cache_path()
        )

    @pyqtSlot()
    def updateSuggestionLists(self):
        """This should be called when the suggestions are ready"""

        self.statusBar.showMessage('Suggestions ready!')
        # self.resetButton.setEnabled(True)
        sender = self.sender()

        if isinstance(sender, SuggestionGetter):
            picks = sender.picks
            strategic_picks = sender.strategic_picks
            candidates = sender.candidates
        else:
            candidates = []
            logging.debug(type(sender))
            logging.debug("Empty or invalid routes generated")
        if candidates:
            self.decisionTreeListWidget.clear()
            for s in picks:
                self.decisionTreeListWidget.addItem(s)
            self.strategicListWidget.clear()
            for c in sorted([]):
                self.strategicListWidget.addItem(c)
            self.solutionListWidget.clear()
            for c in sorted(candidates):
                self.solutionListWidget.addItem(c)
            self.solutionCountLabel.setText(f'({len(candidates)})')
        if self.solutionListWidget.count() > 1:
            self.guessDisplay.setSubmitEnabled(True)
            # self.key_ENTER.setEnabled(True)

        self.guessDisplay.setWithdrawEnabled(True)

    @pyqtSlot(str, tuple)
    def onWordSubmitted(self, word=None, colors=None):
        """Slot to handle wordSubmitted signal."""
        print(f"Received wordSubmitted: '{word} {colors}'")
        if not word or (self.guess.tree and word in self.guess.tree.word_idx):
            if word is not None:
                self.guessDisplay.insertNewRow()
            self.guess.update_guess_result(word, colors)
            self.spawnSuggestionGetter()
        else:
            self.guessDisplay.flashRow()
            self.statusBar.showMessage('Invalid Word choice. Did you enter it correctly?')

    def spawnSuggestionGetter(self):
        # Create a thread that will launch a search
        self.guessDisplay.setSubmitDisabled(True)
        self.guessDisplay.setWithdrawDisabled(True)


        # self.resetButton.setDisabled(True)
        self.statusBar.showMessage('Generating picks...')
        # self.key_ENTER.setDisabled(True)
        getter = SuggestionGetter(self)

        progress_dialog = ProgressDialog(self, cancel_callback=self.onCancelSearch)

        getter.finished.connect(self.updateSuggestionLists)
        getter.finished.connect(progress_dialog.close)

        progress_dialog.show()
        getter.start()


    @pyqtSlot()
    def onCancelSearch(self):
        self.guess.stop()
        self.guessDisplay.removeLastRow()

    @pyqtSlot()
    def onWordWithdrawn(self):
        print('onWordWithdrawn called')
        self.guess.undo_last_guess()
        self.spawnSuggestionGetter()

    @pyqtSlot()
    def onResetGame(self):
        print('onResetGame called')
        self.guessDisplay.clear()
        self.guess.reset()
        self.spawnSuggestionGetter()

    def _on_load_finished(self):
        ...

    def _initGuessManager(self):
        ...

    @pyqtSlot()
    def updateGuessManager(self):
        sender = self.sender()
        if isinstance(sender, GuessManagerInitializer):
            self.guess = sender.guess

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

    # def stop(self):
    #     self.parent().guess.stop()
    #     self._stop_event.set()

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
            profile_name = self.profile_manager.getCurrentProfile()
            profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile_name
            dtree_dir = profile_dir / "dtree"
            dtree_dir.mkdir(parents=True, exist_ok=True)
            tree_file = dtree_dir / f"{self.pick}.txt"
            with tree_file.open("w", encoding="utf-8") as f:
                f.write(routes_to_text(self.routes))
            logging.debug(f"Decision tree saved to {tree_file}")
            self.ready.emit(self.pick, True)
        except Exception as e:
            logging.error(f"Failed to generate decision tree for {self.pick}: {e}")
            self.ready.emit(self.pick, False)

    def stop(self):
        self.guess_manager.stop()

class UpperCaseValidator(QValidator):
    def __init__(self, word_length, parent=None):
        super().__init__(parent)
        self.word_length = word_length

    def validate(self, string, pos):
        if len(string) == self.word_length and string.isalpha():
            return QValidator.State.Acceptable, string.upper(), pos
        elif string == '' or string.isalpha():
            return QValidator.State.Intermediate, string.upper(), pos
        else:
            return QValidator.State.Invalid, string.upper(), pos

class UpperCaseDelegate(QItemDelegate):
    def __init__(self, word_length, parent=None):
        super().__init__(parent)
        self.current_index = None
        self.word_length = word_length

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(UpperCaseValidator(self.word_length, editor))
        editor.setPlaceholderText('Enter a word...')
        self.current_index = index
        return editor

class NewProfileDialog(QDialog, Ui_NewProfile):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setupUi(self)

    def accept(self):
        if not self.nameEdit.text().strip():
            QMessageBox.warning(self, "Invalid Name", "Profile name cannot be empty.")
            return
        super().accept()

class BatchAddDialog(QDialog, Ui_BatchAdd):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setupUi(self)
        self.addWordsEdit.extraContextActions.append(self.actionFormat)
        self.actionFormat.triggered.connect(self.formatText)

    def showEvent(self, event):
        super().showEvent(event)
        self.populateWords()

    def populateWords(self):
        self.addWordsEdit.clear()
        parent = self.parent()
        if hasattr(parent, 'picksList') and self in (parent.managePicksDialog, parent.manageCandidatesDialog):
            target_list = parent.picksList if self is parent.managePicksDialog else parent.candidatesList
            words = [target_list.item(i).text() for i in range(target_list.count()) if target_list.item(i).text().strip()]
            self.addWordsEdit.setPlainText('\n'.join(words))
            self.addWordsEdit.moveCursor(QTextCursor.MoveOperation.End)

    def formatText(self):
        text = self.addWordsEdit.toPlainText()
        words = {word.upper() for word in re.findall(r'[a-zA-Z]+', text)}
        new_text = '\n'.join(sorted(words)) + '\n'
        self.addWordsEdit.setPlainText(new_text)
        self.addWordsEdit.moveCursor(QTextCursor.MoveOperation.End)

    def accept(self):
        self.formatText()
        text = self.addWordsEdit.toPlainText()
        words = [word.strip().upper() for word in text.split("\n") if word.strip()]
        parent = self.parent()
        if words and hasattr(parent, 'picksList') and self in (parent.managePicksDialog, parent.manageCandidatesDialog):
            profile = parent.profile_manager.modifyProfile(parent.profile_manager.getCurrentProfile())
            target_list = parent.picksList if self is parent.managePicksDialog else parent.candidatesList
            target_list.clear()
            if self is parent.manageCandidatesDialog:
                legal_picks = set(profile.picks)
                for word in words:
                    if len(word) == parent.word_length and word.isalpha() and word not in legal_picks:
                        parent.picksList.addItem(word)
                        profile.picks.append(word)
                        profile.dirty = True
            for word in words:
                if len(word) == parent.word_length and word.isalpha():
                    target_list.addItem(word)
                    if self is parent.managePicksDialog and word not in profile.picks:
                        profile.picks.append(word)
                        profile.dirty = True
                    elif self is parent.manageCandidatesDialog and word not in profile.candidates:
                        profile.candidates.append(word)
                        profile.dirty = True
            parent.updateCountLabels()
            parent.is_modified = True
        super().accept()

class MainPreferences(QDialog, Ui_preferences):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile_manager = parent.profile_manager
        self.word_length = 5
        self.guess_manager = None
        self.is_modified = False
        self.default_icon = QIcon.fromTheme("emblem-default", QIcon())  # Fallback to empty icon
        self.initUI()
        self.loadSettings()

    def initUI(self):
        self.setupUi(self)
        logging.debug(f"initUI: QComboBox item count before clear: {self.profileComboBox.count()}")
        self.profileComboBox.clear()
        logging.debug(f"initUI: QComboBox item count after clear: {self.profileComboBox.count()}")
        self.profileComboBox.setEditable(True)
        self.profileComboBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.addInitialPickButton.clicked.connect(self.addInitialPick)
        self.addPickButton.clicked.connect(self.addPick)
        self.addCandidateButton.clicked.connect(self.addCandidate)
        self.removeInitialPickButton.clicked.connect(self.removeInitialPick)
        self.removePickButton.clicked.connect(self.removePick)
        self.removeCandidateButton.clicked.connect(self.removeCandidate)
        self.addProfileButton.clicked.connect(self.addProfile)
        self.removeProfileButton.clicked.connect(self.removeProfile)
        self.setDefaultProfileButton.clicked.connect(self.setDefaultProfile)
        self.copyProfileButton.clicked.connect(self.copyProfile)
        self.removeTreeButton.clicked.connect(self.removeDecisionTree)
        self.exploreTreeButton.clicked.connect(self.exploreTree)
        self.manageCandidatesDialog = BatchAddDialog(self)
        self.managePicksDialog = BatchAddDialog(self)
        self.manageCandidatesButton.clicked.connect(self.manageCandidatesDialog.show)
        self.managePicksButton.clicked.connect(self.managePicksDialog.show)
        delegate_initial = UpperCaseDelegate(self.word_length, self.initialPicksList)
        delegate_initial.closeEditor.connect(self.onCloseInitPicksEditor)
        self.initialPicksList.setItemDelegate(delegate_initial)
        delegate_picks = UpperCaseDelegate(self.word_length, self.picksList)
        delegate_picks.closeEditor.connect(self.onClosePicksEditor)
        self.picksList.setItemDelegate(delegate_picks)
        delegate_candidates = UpperCaseDelegate(self.word_length, self.candidatesList)
        delegate_candidates.closeEditor.connect(self.onCloseCandidatesEditor)
        self.candidatesList.setItemDelegate(delegate_candidates)
        # Initialize chartTreeButton as disabled
        self.chartTreeButton.setEnabled(False)
        self.removeTreeButton.setEnabled(False)
        self.initialPicksList.itemSelectionChanged.connect(self.onInitialPicksListSelectionChanged)
        self.chartTreeButton.clicked.connect(self.onChartTreeButtonClicked)
        self.profileComboBox.activated.connect(self.onProfileChanged)
        self.buttonBox.accepted.connect(self.onOK)
        self.buttonBox.rejected.connect(self.onCancel)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.onApply)
        # Disable default button to prevent Enter key from accepting dialog
        self.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setAutoDefault(False)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Apply).setAutoDefault(False)

        delegate = MultiBadgeDelegate(self.treeWidget, badge_size=32, radius=6, font_px=18, spacing=3, left_padding=0)
        self.treeWidget.setItemDelegateForColumn(0, delegate)
        self.treeWidget.setIndentation(35)

    def keyPressEvent(self, event):
        logging.debug(f"MainPreferences keyPressEvent: key={event.key()}, focusWidget={self.focusWidget()}")
        if event.key() == Qt.Key.Key_Escape:
            logging.debug("Esc key pressed in MainPreferences, triggering closeEvent")
            self.closeEvent(QCloseEvent())
            return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.profileComboBox.hasFocus() or self.profileComboBox.lineEdit().hasFocus():
                self.renameProfile()
                event.accept()  # Consume the Enter key event
                return
        super().keyPressEvent(event)

    def getCurrentModifiedProfile(self) -> Profile:
        """Get or create the current profile in modified, ensuring correct profile is updated."""
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            logging.debug("No profile selected for modification")
            raise ValueError("No profile selected")
        name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        if not name:
            logging.debug("No valid profile name for modification")
            raise ValueError("Invalid profile name")
        logging.debug(f"Getting modified profile for: {name}")
        return self.profile_manager.modifyProfile(name)

    def eventFilter(self, obj, event):
        if obj == self.profileComboBox.lineEdit() and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.renameProfile()
                return True  # Consume the Enter key event
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        logging.debug("MainPreferences closeEvent triggered")
        if self.is_modified or self.profile_manager.has_pending_changes():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Apply them?",
                QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Apply:
                self.onApply()
            elif reply == QMessageBox.StandardButton.Discard:
                self.onCancel()
            else:
                event.ignore()
                return
        super().closeEvent(event)

    def updateCountLabels(self):
        """Update candidateCountLabel and picksCountLabel with current counts."""
        candidates_count = self.candidatesList.count()
        picks_count = self.picksList.count()
        self.candidatesCountLabel.setText(f"({candidates_count})")
        self.picksCountLabel.setText(f"({picks_count})")
        logging.debug(f"Updated labels: Candidates ({candidates_count}), Picks ({picks_count})")

    def getUniqueProfileName(self, base_name):
        """Generate a unique profile name by appending (N) if necessary."""
        profiles = [self.profileComboBox.itemData(i, Qt.ItemDataRole.UserRole) for i in range(self.profileComboBox.count())]
        if base_name not in profiles:
            return base_name
        i = 1
        while f"{base_name} ({i})" in profiles:
            i += 1
        return f"{base_name} ({i})"

    @pyqtSlot()
    def onInitialPicksListSelectionChanged(self):
        """Enable chartTreeButton if a word is selected in initialPicksList, disable otherwise."""
        has_selection = len(self.initialPicksList.selectedItems()) > 0
        self.chartTreeButton.setEnabled(has_selection)
        logging.debug(f"chartTreeButton enabled: {has_selection}")

    @pyqtSlot()
    def onChartTreeButtonClicked(self):
        """Generate a decision tree rule set for the selected word in initialPicksList."""
        selected_items = self.initialPicksList.selectedItems()
        if not selected_items:
            logging.debug("No word selected for decision tree generation")
            return
        # Check if an editor is open for the selected item
        selected_item = selected_items[0]
        selected_index = self.initialPicksList.indexFromItem(selected_item)
        # Check if an editor is open and retrieve its text
        editor_text = None
        if self.initialPicksList.isPersistentEditorOpen(selected_item):
            logging.debug("Editor open for selected item, retrieving text")
            editor = self.initialPicksList.itemWidget(selected_item)
            if isinstance(editor, QLineEdit):
                editor_text = editor.text().strip().upper()
                logging.debug(f"Editor text: {editor_text}")
        if editor_text:
            if len(editor_text) != self.word_length or not editor_text.isalpha():
                logging.debug(f"Invalid editor text: {editor_text}")
                QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
                self.initialPicksList.closePersistentEditor(selected_item)
                self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                self.addInitialPickButton.setEnabled(True)
                return
            legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count())}
            if editor_text not in legal_picks:
                reply = QMessageBox.question(
                    self, "Add to Picks?",
                    f"'{editor_text}' is not in the legal picks. Add it to picks.txt?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.picksList.addItem(editor_text)
                    profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
                    profile.picks.append(editor_text)
                    profile.dirty = True
                    self.updateCountLabels()
                else:
                    logging.debug(f"User declined to add {editor_text} to picks")
                    self.initialPicksList.closePersistentEditor(selected_item)
                    self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                    self.addInitialPickButton.setEnabled(True)
                    return
            selected_item.setText(f"{editor_text} (active)")
            self.initialPicksList.closePersistentEditor(selected_item)
            self.addInitialPickButton.setEnabled(True)
        pick = selected_item.text().split(" (")[0].strip()
        if not pick:
            logging.debug("Empty word selected for decision tree generation")
            QMessageBox.warning(self, "Invalid Word", "The selected word is empty or invalid.")
            return
        profile_name = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
        logging.debug(f"Generating decision tree for word: {pick} in profile: {profile_name}")
        self.spawnDecisionTreeRoutesGetter(pick)

    @pyqtSlot(str, bool)
    def updateDecisionTrees(self, pick, success):
        """Update decisionTreeList and initialPicksList after DecisionTreeRoutesGetter finishes."""
        parent = self.parent()
        self.chartTreeButton.setEnabled(True)
        if success:
            parent.statusBar.showMessage(f"Decision tree generated for {pick}")
            # Add to decisionTreeList if not already present
            if pick not in [self.decisionTreeList.item(i).text() for i in range(self.decisionTreeList.count())]:
                self.decisionTreeList.addItem(pick)
            for i in range(self.initialPicksList.count()):
                if self.initialPicksList.item(i).text() == pick:
                    self.initialPicksList.takeItem(i)
                    break
            self.saveSettings()
        else:
            parent.statusBar.showMessage(f"Failed to generate decision tree for {pick}")
            QMessageBox.warning(self, "Error", f"Failed to generate decision tree for '{pick}'")

    @pyqtSlot()
    def removeDecisionTree(self):
        selected_items = self.decisionTreeList.selectedItems()
        if not selected_items:
            logging.debug("No decision tree selected for removal")
            QMessageBox.warning(self, "No Selection", "Please select a decision tree to remove.")
            return
        word = selected_items[0].text()
        profile_name = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.modifyProfile(profile_name, profile_name)
        dtree_dir = self.profile_manager.app_data_path / "profiles" / profile_name / "dtree"
        tree_file = dtree_dir / f"{word}.txt"
        if tree_file.exists():
            try:
                tree_file.unlink()
                logging.debug(f"Deleted decision tree file: {tree_file}")
                if word in profile.dt:
                    del profile.dt[word]
                    profile.dirty = True
            except OSError as e:
                logging.error(f"Failed to delete decision tree file {tree_file}: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete decision tree for '{word}'.")
                return
        # Remove from decisionTreeList
        self.decisionTreeList.takeItem(self.decisionTreeList.currentRow())
        if word not in [self.initialPicksList.item(i).text().split(" (")[0] for i in range(self.initialPicksList.count())]:
            self.initialPicksList.addItem(f"{word} (active)")
            profile.initial_picks.append(word)
            profile.dirty = True
        self.is_modified = True
        self.guess_manager = None
        logging.debug("Invalidated guess_manager due to decision tree removal")
        self.parent().statusBar.showMessage(f"Removed decision tree for {word}")

    def loadSettings(self):
        self.profileComboBox.clear()
        default_profile = self.profile_manager.getDefaultProfile()
        profile_names = self.profile_manager.getProfileNames()
        for name in profile_names:
            self.profileComboBox.addItem(name, userData=name)
            index = self.profileComboBox.count() - 1
            if name == default_profile:
                self.profileComboBox.setItemIcon(index, self.default_icon)
            else:
                self.profileComboBox.setItemIcon(index, QIcon())
        current_profile = self.profile_manager.getCurrentProfile()
        if current_profile:
            index = self.profileComboBox.findData(current_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
            else:
                self.profileComboBox.setCurrentIndex(0)
                self.profile_manager.setCurrentProfile(profile_names[0] if profile_names else None)
        else:
            if profile_names:
                self.profileComboBox.setCurrentIndex(0)
                self.profile_manager.setCurrentProfile(profile_names[0])
        self.loadProfileSettings(self.profileComboBox.currentIndex())
        logging.debug(f"loadSettings completed, profileComboBox items: {self.profileComboBox.count()}")

    @pyqtSlot(int)
    def loadProfileSettings(self, index: int):
        if index < 0:
            return
        name = self.profileComboBox.itemData(index, Qt.ItemDataRole.UserRole)
        if not name:
            logging.debug(f"No valid profile name at index {index}")
            return
        logging.debug(f"Loading profile settings for: {name}")
        self.profile_manager.setCurrentProfile(name)  # Ensure current_profile is updated
        profile = self.profile_manager.loadProfile(name)
        self.word_length = profile.word_length
        self.initialPicksList.clear()
        for pick in profile.initial_picks:
            item = QListWidgetItem(pick)
            self.initialPicksList.addItem(item)
        self.picksList.clear()
        for pick in profile.picks:
            item = QListWidgetItem(pick)
            self.picksList.addItem(item)
        self.candidatesList.clear()
        for candidate in profile.candidates:
            item = QListWidgetItem(candidate)
            self.candidatesList.addItem(item)
        self.decisionTreeList.clear()
        for pick in profile.dt:
            self.decisionTreeList.addItem(pick)
        self.updateDelegates()
        self.updateCountLabels()
        self.picksList.repaint()
        self.candidatesList.repaint()
        logging.debug(f"Loaded profile settings: {name}, initial_picks: {profile.initial_picks}, picks: {profile.picks}, candidates: {profile.candidates}, word_length: {self.word_length}")
        logging.debug(f"ComboBox state: items={self.profileComboBox.count()}, currentIndex={self.profileComboBox.currentIndex()}, currentText={self.profileComboBox.currentText()}")

    @pyqtSlot(int)
    def onProfileChanged(self, index: int):
        """Handle profile switch via profileComboBox.activated signal."""
        self.loadProfileSettings(index)
        self.is_modified = True
        self.parent().resetGuessManager()
        logging.debug(f"Profile changed to index {index}, reset guess_manager and spawned suggestion getter")

    @pyqtSlot()
    def onApply(self):
        logging.debug("onApply called")
        self.profile_manager.commitChanges()
        self.is_modified = False
        self.parent().resetGuessManager()

    def updateDelegates(self):
        delegate_initial = UpperCaseDelegate(self.word_length, self.initialPicksList)
        delegate_initial.closeEditor.connect(self.onCloseInitPicksEditor)
        self.initialPicksList.setItemDelegate(delegate_initial)
        delegate_picks = UpperCaseDelegate(self.word_length, self.picksList)
        delegate_picks.closeEditor.connect(self.onClosePicksEditor)
        self.picksList.setItemDelegate(delegate_picks)
        delegate_candidates = UpperCaseDelegate(self.word_length, self.candidatesList)
        delegate_candidates.closeEditor.connect(self.onCloseCandidatesEditor)
        self.candidatesList.setItemDelegate(delegate_candidates)

    @pyqtSlot()
    def renameProfile(self):
        logging.debug("renameProfile called")
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            logging.debug("No profile selected for renaming")
            return
        old_name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        new_name = self.profileComboBox.lineEdit().text().strip()
        if not new_name or new_name == old_name:
            logging.debug(f"Invalid or unchanged new name: '{new_name}'")
            self.profileComboBox.lineEdit().setText(old_name)  # Restore old name
            return
        # Generate unique name if conflict
        new_name = self.getUniqueProfileName(new_name)
        logging.debug(f"Renaming profile from {old_name} to {new_name}")
        self.profileComboBox.blockSignals(True)
        try:
            if old_name in self.profile_manager.modified:
                profile = self.profile_manager.modified.pop(old_name)
            else:
                profile = self.profile_manager.loadProfile(old_name)
            profile.dirty = True
            profile.original_name = old_name
            self.profile_manager.modified[new_name] = profile
            self.profile_manager.setCurrentProfile(new_name)
            was_default = old_name == self.profile_manager.getDefaultProfile()
            if was_default:
                self.profile_manager.setDefaultProfile(new_name)
            self.profileComboBox.setItemText(current_index, new_name)
            self.profileComboBox.setItemData(current_index, new_name, Qt.ItemDataRole.UserRole)
            self.profileComboBox.setItemIcon(current_index, self.default_icon if was_default else QIcon())
            self.profileComboBox.lineEdit().setText(new_name)
            self.profileComboBox.clearEditText()
            self.loadProfileSettings(current_index)
        finally:
            self.profileComboBox.blockSignals(False)
        self.parent().statusBar.showMessage(f"Renamed profile from {old_name} to {new_name}")

    @pyqtSlot()
    def removeProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            return
        if self.profileComboBox.count() == 1:
            QMessageBox.warning(self, "Cannot Remove Profile", "Cannot remove the last profile.")
            return
        profile = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Remove Profile",
            f"Are you sure you want to remove the profile '{profile}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return
        logging.debug(f"Removing profile {profile}")
        self.profile_manager.deleteProfile(profile)
        self.profileComboBox.blockSignals(True)
        try:
            self.profileComboBox.removeItem(current_index)
            default_profile = self.profile_manager.getDefaultProfile()
            index = self.profileComboBox.findData(default_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
            else:
                self.profileComboBox.setCurrentIndex(0)
            new_profile = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
            self.profile_manager.setCurrentProfile(new_profile)
            # Update icons for remaining profiles
            for i in range(self.profileComboBox.count()):
                name = self.profileComboBox.itemData(i, Qt.ItemDataRole.UserRole)
                self.profileComboBox.setItemIcon(i, self.default_icon if name == default_profile else QIcon())
        finally:
            self.profileComboBox.blockSignals(False)
        self.loadProfileSettings(self.profileComboBox.currentIndex())
        self.is_modified = True

    @pyqtSlot(QListWidgetItem)
    def validateInitialPick(self, item):
        text = item.text().split(" (")[0].strip().upper()
        if not text:
            self.initialPicksList.takeItem(self.initialPicksList.row(item))
            return
        profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.initialPicksList.takeItem(self.initialPicksList.row(item))
            return
        legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count())}
        if text not in legal_picks:
            reply = QMessageBox.question(
                self, "Add to Picks?",
                f"'{text}' is not in the legal picks. Add it to picks.txt?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.picksList.addItem(text)
                profile.picks.append(text)
                profile.dirty = True
                self.updateCountLabels()
            else:
                self.initialPicksList.takeItem(self.initialPicksList.row(item))
                return
        item.setText(f"{text} (active)")
        if text not in profile.initial_picks:
            profile.initial_picks.append(text)
            profile.dirty = True
        self.is_modified = True

    @pyqtSlot(QListWidgetItem)
    def validatePick(self, item):
        """Validate and normalize the pick."""
        text = item.text().strip().upper()
        if not text:
            self.picksList.takeItem(self.picksList.row(item))
            self.updateCountLabels()
            return
        profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.picksList.takeItem(self.picksList.row(item))
            self.updateCountLabels()
            return
        if text not in profile.picks:
            profile.picks.append(text)
            profile.dirty = True
        self.is_modified = True

    @pyqtSlot(QListWidgetItem)
    def validateCandidate(self, item):
        """Validate and normalize the candidate, adding to picksList if valid."""
        text = item.text().strip().upper()
        if not text:
            self.candidatesList.takeItem(self.candidatesList.row(item))
            self.updateCountLabels()
            return
        profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.candidatesList.takeItem(self.candidatesList.row(item))
            self.updateCountLabels()
            return
        legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count())}
        if text not in legal_picks:
            self.picksList.addItem(text)
            profile.picks.append(text)
            profile.dirty = True
            self.updateCountLabels()
        if text not in profile.candidates:
            profile.candidates.append(text)
            profile.dirty = True
        self.is_modified = True

    @pyqtSlot()
    def removePick(self):
        profile = self.getCurrentModifiedProfile()
        current_item = self.picksList.currentItem()
        if current_item:
            text = current_item.text()
            if text in profile.picks:
                profile.picks.remove(text)
                profile.dirty = True
            self.picksList.takeItem(self.picksList.currentRow())
            self.is_modified = True
            logging.debug(f"Removed pick {text} from profile {self.profile_manager.getCurrentProfile()}")

    @pyqtSlot()
    def savePicksToFile(self):
        profile_name = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.modifyProfile(profile_name)
        profile.picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        profile.dirty = True
        self.is_modified = True

    @pyqtSlot()
    def addInitialPick(self):
        """Add a new item to initialPicksList and enter edit mode."""
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addInitialPickButton.setDisabled(True)
        profile = self.profile_manager.getCurrentProfile()
        self.initialPicksList.addItem(new_item)
        self.initialPicksList.scrollToBottom()
        self.initialPicksList.setCurrentItem(new_item)
        self.initialPicksList.setFocus()
        try:
            self.initialPicksList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for initialPicksList: {e}")
        self.is_modified = True

    @pyqtSlot()
    def onOK(self):
        logging.debug("onOK called")
        self.onApply()
        self.parent().resetGuessManager()
        self.parent().spawnSuggestionGetter()
        self.accept()

    @pyqtSlot()
    def onCancel(self):
        logging.debug("onCancel called")
        self.profile_manager.modified.clear()
        self.profile_manager.to_delete.clear()
        self.profile_manager._default_profile = self.profile_manager.settings.value("default_profile", defaultValue=None)
        self.is_modified = False
        self.reject()

    @pyqtSlot()
    def addPick(self):
        """Add a new item to picksList and enter edit mode."""
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addPickButton.setDisabled(True)
        profile = self.profile_manager.getCurrentProfile()
        self.picksList.addItem(new_item)
        self.picksList.scrollToBottom()
        self.picksList.setCurrentItem(new_item)
        self.picksList.setFocus()
        try:
            self.picksList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for picksList: {e}")
        self.updateCountLabels()
        self.is_modified = True

    @pyqtSlot()
    def addCandidate(self):
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addCandidateButton.setDisabled(True)
        profile = self.profile_manager.getCurrentProfile()
        self.candidatesList.addItem(new_item)
        self.candidatesList.scrollToBottom()
        self.candidatesList.setCurrentItem(new_item)
        self.candidatesList.setFocus()
        try:
            self.candidatesList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for candidatesList: {e}")
        self.updateCountLabels()
        self.is_modified = True

    @pyqtSlot()
    def removeInitialPick(self):
        profile = self.getCurrentModifiedProfile()
        current_item = self.initialPicksList.currentItem()
        if current_item:
            text = current_item.text()
            if text in profile.initial_picks:
                profile.initial_picks.remove(text)
                profile.dirty = True
            self.initialPicksList.takeItem(self.initialPicksList.currentRow())
            self.is_modified = True
            logging.debug(f"Removed initial pick {text} from profile {self.profile_manager.getCurrentProfile()}")

    @pyqtSlot()
    def setDefaultProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            return
        profile_name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        if profile_name == self.profile_manager.getDefaultProfile():
            logging.debug(f"Profile {profile_name} is already default, skipping")
            return
        self.profile_manager.setDefaultProfile(profile_name)
        for i in range(self.profileComboBox.count()):
            name = self.profileComboBox.itemData(i, Qt.ItemDataRole.UserRole)
            self.profileComboBox.setItemIcon(i, self.default_icon if name == profile_name else QIcon())
        self.parent().statusBar.showMessage(f"Set {profile_name} as default profile")
        self.is_modified = True

    @pyqtSlot()
    def removeCandidate(self):
        profile = self.getCurrentModifiedProfile()
        current_item = self.candidatesList.currentItem()
        if current_item:
            text = current_item.text()
            if text in profile.candidates:
                profile.candidates.remove(text)
                profile.dirty = True
            self.candidatesList.takeItem(self.candidatesList.currentRow())
            self.is_modified = True
            logging.debug(f"Removed candidate {text} from profile {self.profile_manager.getCurrentProfile()}")

    @pyqtSlot()
    def addProfile(self):
        dialog = NewProfileDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.nameEdit.text().strip()
            name = self.getUniqueProfileName(name)
            length = dialog.lengthSpinBox.value()
            logging.debug(f"Adding new profile: {name}")
            profile = Profile(word_length=length, game_type=GameType.WORDLE, dirty=True)
            self.profile_manager.modified[name] = profile
            self.profile_manager.setCurrentProfile(name)
            self.profileComboBox.blockSignals(True)
            try:
                self.profileComboBox.addItem(name, userData=name)
                index = self.profileComboBox.count() - 1
                self.profileComboBox.setCurrentIndex(index)
                default_profile = self.profile_manager.getDefaultProfile()
                self.profileComboBox.setItemIcon(index, self.default_icon if name == default_profile else QIcon())
            finally:
                self.profileComboBox.blockSignals(False)
            self.loadProfileSettings(self.profileComboBox.currentIndex())
            self.is_modified = True

    @pyqtSlot()
    def copyProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            logging.debug("No profile selected to copy")
            QMessageBox.warning(self, "No Profile Selected", "Please select a profile to copy.")
            return
        source_profile = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        new_name = self.getUniqueProfileName(f"Copy of {source_profile}")
        logging.debug(f"Copying profile {source_profile} to {new_name}")
        profile = self.profile_manager.loadProfile(source_profile)
        profile.dirty = True
        self.profile_manager.modified[new_name] = profile
        self.profile_manager.setCurrentProfile(new_name)
        self.profileComboBox.blockSignals(True)
        try:
            self.profileComboBox.addItem(new_name, userData=new_name)
            index = self.profileComboBox.count() - 1
            self.profileComboBox.setCurrentIndex(index)
            default_profile = self.profile_manager.getDefaultProfile()
            self.profileComboBox.setItemIcon(index, self.default_icon if new_name == default_profile else QIcon())
            logging.debug(f"Added copied profile {new_name} to QComboBox at index {index}")
        finally:
            self.profileComboBox.blockSignals(False)
        self.loadProfileSettings(self.profileComboBox.currentIndex())
        self.parent().statusBar.showMessage(f"Copied profile {source_profile} to {new_name}")
        self.is_modified = True

    @pyqtSlot()
    def saveSettings(self):
        profile_name = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.modifyProfile(profile_name)
        profile.picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        profile.candidates = [self.candidatesList.item(i).text() for i in range(self.candidatesList.count())]
        profile.initial_picks = [
            self.initialPicksList.item(i).text().split(" (")[0]
            for i in range(self.initialPicksList.count())
        ]
        profile.word_length = self.word_length
        profile.dirty = True
        self.is_modified = True

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onCloseInitPicksEditor(self, editor, hint):
        self.onCloseEditor(editor, hint)
        self.addInitialPickButton.setEnabled(True)

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onClosePicksEditor(self, editor, hint):
        self.onCloseEditor(editor, hint)
        self.addPickButton.setEnabled(True)

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onCloseCandidatesEditor(self, editor, hint):
        self.onCloseEditor(editor, hint)
        self.addCandidateButton.setEnabled(True)

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onCloseEditor(self, editor, hint):
        delegate = self.sender()
        list_widget = delegate.parent()
        if isinstance(delegate, UpperCaseDelegate) and delegate.current_index.isValid():
            index = delegate.current_index
            model = index.model()
            item_text = model.data(index)
            if index.isValid() and not item_text.strip():
                editor.clear()
                model.removeRow(index.row())
            self.updateCountLabels()

    def spawnDecisionTreeRoutesGetter(self, pick):
        """Start a DecisionTreeRoutesGetter thread to generate a decision tree for the given pick."""
        parent = self.parent()
        parent.statusBar.showMessage(f"Generating decision tree for {pick}...")

        # Create a thread that will launch a search
        self.chartTreeButton.setDisabled(True)
        if self.guess_manager is None:
            current_profile = self.profile_manager.getCurrentProfile()
            profile = self.profile_manager.loadProfile(current_profile)
            self.guess_manager = DecisionTreeGuessManager(
                profile.picks,
                profile.candidates,
                length=profile.word_length,
                cache_path=self.profile_manager.app_cache_path()
            )
            logging.debug(f"Created new DecisionTreeGuessManager for pick: {pick}")
        getter = DecisionTreeRoutesGetter(self.profile_manager, pick, self.guess_manager, self)
        progress_dialog = ProgressDialog(self, cancel_callback=getter.stop)
        getter.ready.connect(self.updateDecisionTrees)
        getter.finished.connect(progress_dialog.close)
        progress_dialog.show()
        getter.start()


    @staticmethod
    def create_tree_widget_items_it(data_dict):
        """
        Iteratively creates QTreeWidgetItem hierarchy from a dictionary.

        :param data_dict: The dictionary to convert into QTreeWidgetItems.
                          Expected top-level: {pick: clue_dict}
                          where pick is an iterable of chars and clue_dict is {clue: value}
        :return: The root QTreeWidgetItem if parent was None, otherwise None.
        """
        color_hex_map = {
            Color.BLACK: "#000000",
            Color.YELLOW: "#c9b458",
            Color.GREEN: "#6aaa64",
            Color.UNKNOWN: "transparent"
        }

        root_item = QTreeWidgetItem()
        pick, clue_dict = next(iter(data_dict.items()))
        root_item.setText(0, ','.join(pick))
        stack = [(root_item, data_dict)]
        end = []

        # Create the item tree structure and set the clue colors of each item
        while stack:
            parent, dt = stack.pop()
            end.append(parent)
            pick, clue_dict = next(iter(dt.items()))
            for clue, new_dt in sorted(clue_dict.items()):
                item = QTreeWidgetItem(parent)
                text = ','.join(f'{char}:{color_hex_map[c]}' for char, c in zip(pick, clue))
                item.setText(0, text)
                if new_dt is not None:
                    stack.append((item,  new_dt))
                else:
                    item.setText(1, '1') # Leaves have value 1

        # Sum the number of leaf decendents under each item
        for item in reversed(end):
            child_leaves = sum(int(item.child(i).text(1)) for i in range(item.childCount()))
            item.setText(1, str(child_leaves))

        return root_item


    @pyqtSlot()
    def exploreTree(self):
        """Generate a decision tree rule set for the selected word in initialPicksList."""

        selected_item = next(iter(self.decisionTreeList.selectedItems()), None)

        if not selected_item:
            logging.debug("No word selected for decision tree generation")
            return

        selected_index = self.decisionTreeList.indexFromItem(selected_item)
        # Check if an editor is open and retrieve its text
        current_profile = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.loadProfile(current_profile)

        tree = {selected_item.text(): profile.dt[selected_item.text()]}


        tree_widget_item = self.create_tree_widget_items_it(tree)
        self.treeWidget.addTopLevelItem(tree_widget_item)
        tree_widget_item.setExpanded(True)


class MultiBadgeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, badge_size=40, radius=6, font_px=20, spacing=6, left_padding=4):
        super().__init__(parent)
        self.badge_size = badge_size
        self.radius = radius
        self.font_px = font_px
        self.spacing = spacing
        self.left_padding = left_padding

    def paint(self, painter, option, index):
        data = index.data()
        if not data:
            super().paint(painter, option, index)
            return

        # Parse "A:#1976D2,B:#388E3C,..." into list of (letter, color)
        pairs = []
        for part in data.split(','):
            part = part.strip()
            if not part:
                continue
            if ':' in part:
                letter, color = part.split(':', 1)
            elif '|' in part:
                letter, color = part.split('|', 1)
            else:
                letter, color = part, "#777"
            pairs.append((letter.strip(), color.strip()))

        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # font = QFont("Monospace")
        font = QFont()
        font.setPixelSize(self.font_px)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()

        # compute start x so badges are left-aligned with optional padding
        x = rect.x() + self.left_padding
        y = rect.y() + (rect.height() - self.badge_size) // 2


        for letter, color in pairs:
            badge_rect = QRect(x, y, self.badge_size, self.badge_size)

            # Draw rounded background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(badge_rect, self.radius, self.radius)

            # Draw letter centered
            painter.setPen(QColor("#ffffff"))
            text_w = fm.horizontalAdvance(letter)
            text_h = fm.height()  # Use full height (ascent + descent)

            # Horizontal centering
            tx = x + (self.badge_size - text_w) // 2
            # Vertical centering: baseline is at ascent above the bottom of the text
            ty = y + (self.badge_size - text_h) // 2 + fm.ascent()

            painter.drawText(tx, ty, letter)
            x += self.badge_size + self.spacing

            # Stop if overflow (optional)
            if x > rect.right():
                break

        painter.restore()

    def sizeHint(self, option, index):
        # Estimate width based on number of badges
        data = index.data() or ""
        count = sum(1 for p in data.split(',') if p.strip())
        if count == 0:
            return QSize(0, 0)
        total_w = self.left_padding + count * self.badge_size + (count - 1) * self.spacing + 4
        total_h = self.badge_size + 4
        return QSize(total_w, total_h)



if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = MainWordLeSmashWindow()
    main.show()
    sys.exit(app.exec())
