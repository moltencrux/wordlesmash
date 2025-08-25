#!/usr/bin/env -S python3 -O
import logging, sys, os
from PyQt6.QtCore import (QCoreApplication, QSettings, QStandardPaths, Qt,
    pyqtSlot, pyqtSignal, QObject, QThread, QModelIndex, QEvent, QTimer
)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QDialog, QListWidgetItem,
    QMessageBox, QItemDelegate, QLineEdit, QListWidget, QFormLayout, QSpinBox,
    QDialogButtonBox
)
from PyQt6.QtGui import QColorConstants, QValidator, QFont, QTextCursor, QCloseEvent
from threading import Event
from importlib.resources import files
from pathlib import Path
from utils import all_files_newer
from solver import GuessManager, Color, DecisionTreeGuessManager
import shutil
import tempfile
import re
from tree_utils import routes_to_text
from itertools import cycle

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
        # Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path, from_imports=True, import_from='ui')
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

class ProfileManager:
    def __init__(self, parent=None, settings=None):
        self.settings = settings if settings is not None else QSettings()
        self.app_data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.app_cache_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        self.current_profile = self.getDefaultProfile()

    def getCurrentProfile(self):
        return self.current_profile

    def getDefaultProfile(self):
        if not self.settings.contains("default_profile"):
            self.setDefaultProfile("Basic")
        return self.settings.value("default_profile")

    def setCurrentProfile(self, profile):
        self.current_profile = profile

    def setDefaultProfile(self, profile):
        self.settings.setValue("default_profile", profile)

    def getPicks(self):
        profile = self.getCurrentProfile()
        picks_file = Path(self.app_data_path) / "profiles" / profile / "picks.txt"
        return picks_file

    def getCandidates(self):
        profile = self.getCurrentProfile()
        candidates_file = Path(self.app_data_path) / "profiles" / profile / "candidates.txt"
        return candidates_file

    def getDecisionTrees(self):
        profile = self.getCurrentProfile()
        profile_dir = Path(self.app_data_path) / "profiles" / profile
        dtree_dir = profile_dir / "dtree"
        return tuple(dtree_dir.glob("*.txt"))

    def getWordLength(self):
        self.settings.beginGroup(f"profiles/{self.getCurrentProfile()}")
        word_length = self.settings.value("word_length", 5, type=int)
        self.settings.endGroup()
        return word_length

    def getTempNamespace(self):
        return f"temp_profiles/{self.getCurrentProfile()}"

    def getTempDir(self, temp_path):
        return temp_path / self.getCurrentProfile()

    def swapWithTemp(self, temp_namespace, temp_dir):
        # Swap QSettings
        self.settings.beginGroup(temp_namespace)
        keys = self.settings.allKeys()
        values = [self.settings.value(key) for key in keys]
        self.settings.endGroup()
        current_group = f"profiles/{self.getCurrentProfile()}"
        self.settings.beginGroup(current_group)
        self.settings.remove("")
        for key, value in zip(keys, values):
            self.settings.setValue(key, value)
        self.settings.endGroup()
        self.settings.beginGroup("temp_profiles")
        self.settings.remove(self.getCurrentProfile())
        self.settings.endGroup()
        self.settings.sync()
        # Swap directories
        current_dir = Path(self.app_data_path) / "profiles" / self.getCurrentProfile()
        temp_profile_dir = self.getTempDir(temp_dir)
        try:
            if current_dir.exists():
                shutil.rmtree(current_dir)
            if temp_profile_dir.exists():
                shutil.move(temp_profile_dir, current_dir)
            logging.debug(f"Swapped temp profile with current: {self.getCurrentProfile()}")
        except OSError as e:
            logging.error(f"Failed to swap temp profile directory {temp_profile_dir} to {current_dir}: {e}")
            raise

    def deleteTemp(self, temp_namespace, temp_dir):
        self.settings.beginGroup(temp_namespace)
        self.settings.remove("")
        self.settings.endGroup()
        self.settings.sync()
        temp_profile_dir = self.getTempDir(temp_dir)
        if temp_profile_dir.exists():
            try:
                shutil.rmtree(temp_profile_dir)
                logging.debug(f"Deleted temp profile directory: {temp_profile_dir}")
            except OSError as e:
                logging.error(f"Failed to delete temp profile directory {temp_profile_dir}: {e}")

class ProgressDialog(QDialog, Ui_ProgressDialog):
    def __init__(self, parent=None, cancel_callback=None):
        super().__init__(parent)
        self.cancel_callback = cancel_callback
        self.initUI()
        self.last_periods = cycle(("    ", " .  ", " .. ", " ...",))  # List of periods to rotate
        self.timer = QTimer(self)  # Initialize QTimer
        self.timer.timeout.connect(self.updateLabel)  # Connect timeout signal to updateLabel method
        self.timer.start(400)  # Start the timer with a 500 ms interval

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
        base_text = self.label.text().rstrip('. ')
        self.label.setText(base_text + next(self.last_periods))


    def onCancelRequested(self):
        self.spinner.setDisabled(True)
        self.label.setText("Canceling routes generation ...")
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


class MainWordLeSmashWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setupUi(self)
        self.settings = QSettings()
        self.profile_manager = ProfileManager(self, self.settings)
        self.guessDisplay.setFocus()
        print(f'{type(self.waitingSpinner) = }')
        self.setSpinnerProperties()
        # self.guess = GuessManager(filename='default_words.txt', length=5)
        self.resetGuessManager()
        self.onWordSubmitted()
        self.guessDisplay.wordSubmitted.connect(self.onWordSubmitted)
        self.guessDisplay.wordWithdrawn.connect(self.onWordWithdrawn)
        self.resetButton.clicked.connect(self.onResetGame)
        self.stopButton.setDisabled(True)
        self.stopButton.clicked.connect(self.onCancelSearch)


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
        self.guess = DecisionTreeGuessManager(self.profile_manager.getPicks(),
                                              self.profile_manager.getCandidates(),
                                              self.profile_manager.getDecisionTrees(),
                                              length=self.profile_manager.getWordLength(),
                                              cache_path=self.profile_manager.app_cache_path)


    @pyqtSlot()
    def updateSuggestionLists(self):
        """This should be called when the suggestions are ready"""

        self.waitingSpinner.stop()
        self.statusBar.showMessage('Suggestions ready!')
        self.stopButton.setDisabled(True)
        self.resetButton.setEnabled(True)
        sender = self.sender()

        if isinstance(sender, SuggestionGetter):
            picks = sender.picks
            strategic_picks = sender.strategic_picks
            candidates = sender.candidates
        else:
            candidates = []
            logging.debug(type(sender))

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
            self.key_ENTER.setEnabled(True)

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
        self.stopButton.setEnabled(True)
        self.resetButton.setDisabled(True)
        self.statusBar.showMessage('Generating picks...')
        self.waitingSpinner.start()
        self.key_ENTER.setDisabled(True)
        getter = SuggestionGetter(self)
        getter.finished.connect(self.updateSuggestionLists)
        getter.start()

    def setSpinnerProperties(self):
        ...
        # self.waitingSpinner.setRoundness(70)
        # self.waitingSpinner.setMinimumTrailOpacity(15)
        # self.waitingSpinner.setTrailFadePercentage(70)
        # self.waitingSpinner.setNumberOfLines(12)
        # self.waitingSpinner.setLineLength(10)
        # self.waitingSpinner.setLineWidth(5)
        # self.waitingSpinner.setInnerRadius(10)
        # self.waitingSpinner.setRevolutionsPerSecond(1)
        # self.waitingSpinner.setColor(QColorConstants.Gray)


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
        self._stop_event = Event()

    def run(self):
        suggestions = self.parent().guess.get_suggestions()
        self.picks, self.strategic_picks, self.candidates = suggestions
        self.ready.emit()

    def stop(self):
        self._stop_event.set()

class DecisionTreeRoutesGetter(QThread):
    ready = pyqtSignal(str, bool)

    def __init__(self, profile_manager, pick, guess_manager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.pick = pick
        self.guess_manager = guess_manager
        self.app_cache_path = profile_manager.app_cache_path
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
            target_list = parent.picksList if self is parent.managePicksDialog else parent.candidatesList
            target_list.clear()
            if self is parent.manageCandidatesDialog:
                # Add valid words to picksList to maintain candidates ⊆ picks
                legal_picks = [parent.picksList.item(i).text() for i in range(parent.picksList.count())]
                for word in words:
                    if len(word) == parent.word_length and word.isalpha() and word not in legal_picks:
                        parent.picksList.addItem(word)
                parent.savePicksToFile()
            for word in words:
                if len(word) == parent.word_length and word.isalpha():
                    target_list.addItem(word)
            parent.updateCountLabels()
            if self is parent.managePicksDialog:
                parent.savePicksToFile()
            elif self is parent.manageCandidatesDialog:
                parent.saveSettings()
        super().accept()

class MainPreferences(QDialog, Ui_preferences):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile_manager = parent.profile_manager
        self.word_length = 5  # Default word length
        self._loading_settings = False
        self.guess_manager = None
        self.temp_namespace = None
        self.temp_dir = None
        self.original_profile = None
        self.is_modified = False
        # self.progress_dialog = None
        self.initUI()
        self.createTempProfile()
    
    def initUI(self):
        self.setupUi(self)
        logging.debug(f"initUI: QComboBox item count before clear: {self.profileComboBox.count()}")
        self.profileComboBox.clear()
        logging.debug(f"initUI: QComboBox item count after clear: {self.profileComboBox.count()}")
        self.profileComboBox.setEditable(True)
        self.profileComboBox.lineEdit().returnPressed.connect(self.renameProfile)
        self.profileComboBox.lineEdit().installEventFilter(self)
        self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
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
        # self.decisionTreeList.itemSelectionChanged.connect(self.onDecisionTreeListSelectionChanged)
        self.chartTreeButton.clicked.connect(self.onChartTreeButtonClicked)
        self.buttonBox.accepted.connect(self.onOK)
        self.buttonBox.rejected.connect(self.onCancel)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.onApply)
        self.loadSettings()

    def keyPressEvent(self, event):
        logging.debug(f"MainPreferences keyPressEvent: key={event.key()}, focusWidget={self.focusWidget()}")
        if event.key() == Qt.Key.Key_Escape:
            logging.debug("Esc key pressed in MainPreferences, triggering closeEvent")
            self.closeEvent(QCloseEvent())
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if watched == self.profileComboBox.lineEdit() and event.type() == QEvent.Type.KeyPress:
            logging.debug(f"MainPreferences eventFilter: key={event.key()}, focusWidget={self.focusWidget()}")
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.renameProfile()
                return True  # Consume the event to prevent dialog closure
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        logging.debug("MainPreferences closeEvent triggered")
        if self.is_modified:
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
        self.profile_manager.deleteTemp(self.temp_namespace, self.temp_dir)
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
        profiles = [self.profileComboBox.itemText(i).rstrip(" ✓") for i in range(self.profileComboBox.count())]
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

    def createTempProfile(self):
        self.original_profile = self.profile_manager.getCurrentProfile()
        self.temp_namespace = f"temp_profiles/{self.original_profile}"
        self.temp_dir = Path(tempfile.mkdtemp(prefix=f"wordle_{self.original_profile}_"))
        logging.debug(f"Creating temp profile: {self.temp_namespace}, dir: {self.temp_dir}")
        # Copy QSettings to temp_profiles/<profile>
        self.profile_manager.settings.beginGroup(f"profiles/{self.original_profile}")
        keys = self.profile_manager.settings.allKeys()
        values = [self.profile_manager.settings.value(key) for key in keys]
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.beginGroup(self.temp_namespace)
        for key, value in zip(keys, values):
            self.profile_manager.settings.setValue(key, value)
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.sync()
        # Copy files to temp directory
        source_dir = Path(self.profile_manager.app_data_path) / "profiles" / self.original_profile
        dest_dir = self.temp_dir / self.original_profile
        dest_dir.mkdir(parents=True, exist_ok=True)
        if source_dir.exists():
            shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)
        else:
            (dest_dir / "picks.txt").touch()
            (dest_dir / "candidates.txt").touch()
        self.is_modified = False

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
                # Validate editor text
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
                            self.savePicksToFile()
                            self.updateCountLabels()
                        else:
                            logging.debug(f"User declined to add {editor_text} to picks")
                            self.initialPicksList.closePersistentEditor(selected_item)
                            self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                            self.addInitialPickButton.setEnabled(True)
                            return
                    # Update item text and close editor
                    selected_item.setText(editor_text)
                    self.initialPicksList.closePersistentEditor(selected_item)
                    self.addInitialPickButton.setEnabled(True)
                else:
                    logging.debug("Editor text is empty")
                    self.initialPicksList.closePersistentEditor(selected_item)
                    self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                    self.addInitialPickButton.setEnabled(True)
                    return
        # Re-check selected items after closing editor
        selected_items = self.initialPicksList.selectedItems()
        if not selected_items:
            logging.debug("No valid word selected after closing editor")
            QMessageBox.warning(self, "Invalid Selection", "Please select a valid word for decision tree generation.")
            return
        pick = selected_items[0].text().strip()
        if not pick:
            logging.debug("Empty word selected for decision tree generation")
            QMessageBox.warning(self, "Invalid Word", "The selected word is empty or invalid.")
            return
        profile_name = self.profileComboBox.currentText().rstrip(" ✓")
        logging.debug(f"Generating decision tree for word: {pick} in profile: {profile_name}")
        self.spawnDecisionTreeRoutesGetter(pick)

    @pyqtSlot(str, bool)
    def updateDecisionTrees(self, pick, success):
        """Update decisionTreeList and initialPicksList after DecisionTreeRoutesGetter finishes."""
        parent = self.parent()
        sender = self.sender()
        # pick = sender.pick
        # success = True
        # if self.progress_dialog:
        #     # self.progress_dialog.close()
        #     self.progress_dialog = None
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
        profile = self.profile_manager.getCurrentProfile()
        logging.debug(f"Removing decision tree for {word} in profile {profile} (temp)")
        dtree_dir = self.temp_dir / profile / "dtree"
        tree_file = dtree_dir / f"{word}.txt"
        if tree_file.exists():
            try:
                tree_file.unlink()
                logging.debug(f"Deleted decision tree file: {tree_file}")
            except OSError as e:
                logging.error(f"Failed to delete decision tree file {tree_file}: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete decision tree for '{word}'.")
                return
        # Remove from decisionTreeList
        self.decisionTreeList.takeItem(self.decisionTreeList.currentRow())
        # Add word to initialPicksList if not present
        if word not in [self.initialPicksList.item(i).text() for i in range(self.initialPicksList.count())]:
            self.initialPicksList.addItem(word)
            logging.debug(f"Added {word} to initialPicksList")
        self.saveSettings()
        self.onDecisionTreeListSelectionChanged()
        self.guess_manager = None
        logging.debug("Invalidated guess_manager due to decision tree removal")
        self.parent().statusBar.showMessage(f"Removed decision tree for {word}")
        self.is_modified = True

    def loadSettings(self):
        logging.debug("Loading settings")
        self.profile_manager.settings.beginGroup("profiles")
        profiles = self.profile_manager.settings.childGroups()
        self.profile_manager.settings.endGroup()
        self.profileComboBox.clear()
        if not profiles:
            profiles = ["Basic"]
        default_profile = self.profile_manager.getDefaultProfile()
        logging.debug(f"Profiles: {profiles}, Default: {default_profile}")
        # Disconnect signals to prevent spurious triggers
        try:
            self.profileComboBox.currentTextChanged.disconnect(self.loadProfileSettings)
        except TypeError:
            pass  # Signal not connected
        try:
            for profile in profiles:
                display_text = f"{profile} ✓" if profile == default_profile else profile
                self.profileComboBox.addItem(display_text, userData=profile)
                logging.debug(f"Added profile {profile} to QComboBox at index {self.profileComboBox.count() - 1}")
            index = self.profileComboBox.findData(default_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
            else:
                self.profileComboBox.setCurrentIndex(0)
            selected_profile = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
            self.profile_manager.setCurrentProfile(selected_profile)
        finally:
            # Reconnect signals
            self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
        self.loadProfileSettings()

    @pyqtSlot(str)
    def loadProfileSettings(self, profile_name=None):
        if self._loading_settings:
            logging.debug(f"Skipping loadProfileSettings for {profile_name} due to recursive call")
            return
        self._loading_settings = True
        try:
            if profile_name is None:
                profile_name = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
            if not profile_name:
                profile_name = "Basic"
            logging.debug(f"Loading profile settings for {profile_name}")
            # Sync ProfileManager with combo box selection
            self.profile_manager.setCurrentProfile(profile_name)
            self.profile_manager.settings.beginGroup(f"profiles/{profile_name}")
            game_type = self.profile_manager.settings.value("game_type", "wordle", type=str)
            self.gameTypeComboBox.setCurrentText(game_type)
            self.word_length = self.profile_manager.getWordLength()
            self.wordLengthDisplayLabel.setText(str(self.word_length))
            initial_picks = self.profile_manager.settings.value("initial_picks", "", type=str)
            logging.debug(f"Initial picks: {initial_picks}")
            self.initialPicksList.clear()
            if initial_picks:
                for pick in initial_picks.split("\n"):
                    if pick.strip():
                        self.initialPicksList.addItem(pick.strip().upper())
            self.profile_manager.settings.endGroup()
            picks_file = self.profile_manager.getPicks()
            self.picksList.clear()
            if picks_file.exists():
                with picks_file.open("r", encoding="utf-8") as f:
                    legal_picks = [line.strip().upper() for line in f if line.strip()]
                    logging.debug(f"Picks loaded: {legal_picks}")
                    for pick in legal_picks:
                        self.picksList.addItem(pick)
            candidates_file = self.profile_manager.getCandidates()
            self.candidatesList.clear()
            if candidates_file.exists():
                with candidates_file.open("r", encoding="utf-8") as f:
                    candidates = [line.strip().upper() for line in f if line.strip()]
                    logging.debug(f"Candidates loaded: {candidates}")
                    for candidate in candidates:
                        self.candidatesList.addItem(candidate)
            dtree_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile_name / "dtree"
            self.decisionTreeList.clear()
            if dtree_dir.exists():
                for file_path in dtree_dir.glob("*.txt"):
                    self.decisionTreeList.addItem(file_path.stem)
            self.updateCountLabels()
            self.updateDelegates()
            # Update chartTreeButton state after loading initialPicksList
            self.onInitialPicksListSelectionChanged()
            # self.onDecisionTreeListSelectionChanged()
            # Invalidate guess_manager on profile switch
            self.guess_manager = None
            logging.debug(f"Cleared guess_manager on profile switch to {profile_name}")
        finally:
            self._loading_settings = False

    @pyqtSlot()
    def onApply(self):
        self.profile_manager.swapWithTemp(self.temp_namespace, self.temp_dir)
        self.temp_namespace = f"temp_profiles/{self.original_profile}"
        self.temp_dir = Path(tempfile.mkdtemp(prefix=f"wordle_{self.original_profile}_"))
        self.createTempProfile()
        self.loadProfileSettings(self.original_profile)
        self.guess_manager = None
        self.is_modified = False
        self.parent().statusBar.showMessage(f"Changes applied for profile {self.original_profile}")

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
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            return
        old_name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        new_name = self.profileComboBox.lineEdit().text().strip()
        if new_name == old_name or not new_name:
            self.profileComboBox.lineEdit().clear()
            return
        # Generate unique name if conflict
        new_name = self.getUniqueProfileName(new_name)
        logging.debug(f"Renaming profile from {old_name} to {new_name}")
        self.profile_manager.settings.beginGroup(self.temp_namespace)
        keys = self.profile_manager.settings.allKeys()
        values = [self.profile_manager.settings.value(key) for key in keys]
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.beginGroup(f"temp_profiles/{new_name}")
        for key, value in zip(keys, values):
            self.profile_manager.settings.setValue(key, value)
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.beginGroup("temp_profiles")
        self.profile_manager.settings.remove(old_name)
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.sync()
        old_dir = self.temp_dir / old_name
        new_dir = self.temp_dir / new_name
        if old_dir.exists():
            old_dir.rename(new_dir)
        self.profile_manager.setCurrentProfile(new_name)
        if self.profile_manager.getDefaultProfile() == old_name:
            self.profile_manager.setDefaultProfile(new_name)
        self.original_profile = new_name
        self.temp_namespace = f"temp_profiles/{new_name}"
        default_profile = self.profile_manager.getDefaultProfile()
        display_text = f"{new_name} ✓" if new_name == default_profile else new_name
        self.profileComboBox.setItemText(current_index, display_text)
        self.profileComboBox.setItemData(current_index, new_name, Qt.ItemDataRole.UserRole)
        logging.debug(f"Renamed profile to {new_name}, reloading settings")
        self.profileComboBox.lineEdit().clear()
        self.loadProfileSettings(new_name)
        self.is_modified = True

    @pyqtSlot()
    def removeProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            return
        profile = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        if profile == "Basic":
            QMessageBox.warning(self, "Cannot Remove Profile", "The 'Basic' profile cannot be removed.")
            return
        reply = QMessageBox.question(
            self, "Remove Profile",
            f"Are you sure you want to remove the profile '{profile}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return
        logging.debug(f"Removing profile {profile}")
        self.profile_manager.settings.beginGroup("profiles")
        self.profile_manager.settings.remove(profile)
        self.profile_manager.settings.endGroup()
        profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile
        if profile_dir.exists():
            shutil.rmtree(profile_dir)
        try:
            self.profileComboBox.currentTextChanged.disconnect(self.loadProfileSettings)
        except TypeError:
            pass
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
        finally:
            self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
        self.loadProfileSettings(new_profile)
        self.createTempProfile()
        self.is_modified = True

    @pyqtSlot(QListWidgetItem)
    def validateInitialPick(self, item):
        """Validate and normalize the initial pick."""
        text = item.text().strip().upper()
        if not text:
            # self.initialPicksList.takeItem(self.initialPicksList.row(item))  # Remove unchanged placeholder
            pass
            return
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.initialPicksList.takeItem(self.initialPicksList.row(item))
            return
        legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count())}
        if text not in legal_picks:
            reply = QMessageBox.question(self, "Add to Picks?", f"'{text}' is not in the legal picks. Add it to picks.txt?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.picksList.addItem(text)
                self.savePicksToFile()
                self.updateCountLabels()
            else:
                self.initialPicksList.takeItem(self.initialPicksList.row(item))
                return

    @pyqtSlot(QListWidgetItem)
    def validatePick(self, item):
        """Validate and normalize the pick."""
        text = item.text().strip().upper()
        if not text:
            self.picksList.takeItem(self.picksList.row(item))
            self.updateCountLabels()
            return
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.picksList.takeItem(self.picksList.row(item))
            self.updateCountLabels()
            return

    @pyqtSlot(QListWidgetItem)
    def validateCandidate(self, item):
        """Validate and normalize the candidate, adding to picksList if valid."""
        text = item.text().strip().upper()
        if not text:
            self.candidatesList.takeItem(self.candidatesList.row(item))
            self.updateCountLabels()
            return
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.candidatesList.takeItem(self.candidatesList.row(item))
            self.updateCountLabels()
            return
        legal_picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        if text not in legal_picks:
            self.picksList.addItem(text)
            self.savePicksToFile()
            self.updateCountLabels()

    @pyqtSlot()
    def removePick(self):
        current_row = self.picksList.currentRow()
        if current_row >= 0:
            profile = self.profile_manager.getCurrentProfile()
            word = self.picksList.item(current_row).text()
            self.picksList.takeItem(current_row)
            # Remove from candidatesList to maintain candidates ⊆ picks
            for i in range(self.candidatesList.count()):
                if self.candidatesList.item(i).text() == word:
                    self.candidatesList.takeItem(i)
                    break
            self.savePicksToFile()
            self.updateCountLabels()
            self.guess_manager = None
            self.is_modified = True

    @pyqtSlot()
    def savePicksToFile(self):
        profile_name = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
        profile_dir = self.temp_dir / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        picks_file = profile_dir / "picks.txt"
        legal_picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        with picks_file.open("w", encoding="utf-8") as f:
            for pick in legal_picks:
                if pick.strip():
                    f.write(pick + "\n")
        logging.debug(f"Saved picks to {picks_file}")

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
        self.onApply()
        self.accept()

    @pyqtSlot()
    def onCancel(self):
        self.profile_manager.deleteTemp(self.temp_namespace, self.temp_dir)
        self.loadProfileSettings(self.original_profile)
        self.guess_manager = None
        self.is_modified = False
        self.parent().statusBar.showMessage(f"Changes discarded for profile {self.original_profile}")
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
        current_row = self.initialPicksList.currentRow()
        if current_row >= 0:
            profile = self.profile_manager.getCurrentProfile()
            self.initialPicksList.takeItem(current_row)
            self.saveSettings()
            self.is_modified = True

    @pyqtSlot()
    def setDefaultProfile(self):
        profile_name = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
        if profile_name == self.profile_manager.getDefaultProfile():
            logging.debug(f"Profile {profile_name} is already default, skipping")
            return
        self.profile_manager.settings.beginGroup(self.temp_namespace)
        self.profile_manager.settings.setValue("default", profile_name)
        self.profile_manager.settings.endGroup()
        self.profile_manager.setDefaultProfile(profile_name)
        for i in range(self.profileComboBox.count()):
            profile = self.profileComboBox.itemData(i, Qt.ItemDataRole.UserRole)
            display_text = f"{profile} ✓" if profile == profile_name else profile
            self.profileComboBox.setItemText(i, display_text)
        self.parent().statusBar.showMessage(f"Set {profile_name} as default profile")
        self.is_modified = True

    @pyqtSlot()
    def removeCandidate(self):
        current_row = self.candidatesList.currentRow()
        if current_row >= 0:
            profile = self.profile_manager.getCurrentProfile()
            self.candidatesList.takeItem(current_row)
            self.saveSettings()
            self.updateCountLabels()
            self.guess_manager = None
            self.is_modified = True

    @pyqtSlot()
    def addProfile(self):
        dialog = NewProfileDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.nameEdit.text().strip()
            name = self.getUniqueProfileName(name)
            length = dialog.lengthSpinBox.value()
            logging.debug(f"Adding new profile: {name}")
            self.profile_manager.settings.beginGroup(f"profiles/{name}")
            self.profile_manager.settings.setValue("word_length", length)
            self.profile_manager.settings.setValue("game_type", "wordle")
            self.profile_manager.settings.setValue("initial_picks", "")
            self.profile_manager.settings.endGroup()
            profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / name
            profile_dir.mkdir(parents=True, exist_ok=True)
            # Create default picks and candidates files
            picks_file = profile_dir / "picks.txt"
            picks_file.touch()
            candidates_file = profile_dir / "candidates.txt"
            candidates_file.touch()
            default_profile = self.profile_manager.getDefaultProfile()
            try:
                self.profileComboBox.currentTextChanged.disconnect(self.loadProfileSettings)
            except TypeError:
                pass
            try:
                display_text = f"{name} ✓" if name == default_profile else name
                self.profileComboBox.addItem(display_text, userData=name)
                self.profileComboBox.setCurrentIndex(self.profileComboBox.count() - 1)
                self.profile_manager.setCurrentProfile(name)
            finally:
                self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
            self.loadProfileSettings(name)
            self.createTempProfile()
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
        # Copy QSettings group
        self.profile_manager.settings.beginGroup(f"profiles/{source_profile}")
        keys = self.profile_manager.settings.allKeys()
        values = [self.profile_manager.settings.value(key) for key in keys]
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.beginGroup(f"profiles/{new_name}")
        for key, value in zip(keys, values):
            self.profile_manager.settings.setValue(key, value)
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.sync()
        # Copy profile directory
        source_dir = Path(self.profile_manager.app_data_path) / "profiles" / source_profile
        dest_dir = Path(self.profile_manager.app_data_path) / "profiles" / new_name
        if source_dir.exists():
            shutil.copytree(source_dir, dest_dir)
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / "picks.txt").touch()
            (dest_dir / "candidates.txt").touch()
        # Update profileComboBox
        default_profile = self.profile_manager.getDefaultProfile()
        try:
            self.profileComboBox.currentTextChanged.disconnect(self.loadProfileSettings)
        except TypeError:
            pass
        try:
            display_text = f"{new_name} ✓" if new_name == default_profile else new_name
            self.profileComboBox.addItem(display_text, userData=new_name)
            self.profileComboBox.setCurrentIndex(self.profileComboBox.count() - 1)
            logging.debug(f"Added copied profile {new_name} to QComboBox at index {self.profileComboBox.count() - 1}")
            self.profile_manager.setCurrentProfile(new_name)
        finally:
            self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
        self.loadProfileSettings(new_name)
        self.createTempProfile()
        self.parent().statusBar.showMessage(f"Copied profile {source_profile} to {new_name}")
        self.is_modified = True

    @pyqtSlot()
    def saveSettings(self):
        profile_name = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
        self.profile_manager.settings.beginGroup(self.temp_namespace)
        self.profile_manager.settings.setValue("word_length", self.word_length)
        self.profile_manager.settings.setValue("game_type", "wordle")
        initial_picks = [self.initialPicksList.item(i).text() for i in range(self.initialPicksList.count())]
        self.profile_manager.settings.setValue("initial_picks", "\n".join(initial_picks))
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.sync()

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
        # self.statusBar.showMessage('Generating picks...')
        # Create guess_manager if None or outdated
        if self.guess_manager is None:
            self.guess_manager = DecisionTreeGuessManager(
                self.profile_manager.getPicks(),
                self.profile_manager.getCandidates(),
                length=self.profile_manager.getWordLength(),
                cache_path=self.profile_manager.app_cache_path
            )
            logging.debug(f"Created new DecisionTreeGuessManager for pick: {pick}")
        getter = DecisionTreeRoutesGetter(self.profile_manager, pick, self.guess_manager, self)
        progress_dialog = ProgressDialog(self, cancel_callback=getter.stop)
        getter.ready.connect(self.updateDecisionTrees)
        getter.finished.connect(progress_dialog.close)
        progress_dialog.show()
        getter.start()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = MainWordLeSmashWindow()
    main.show()
    sys.exit(app.exec())
