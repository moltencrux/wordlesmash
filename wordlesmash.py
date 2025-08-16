#!/usr/bin/env -S python3 -O
import logging, sys, os
from PyQt6.QtCore import (QCoreApplication, QSettings, QStandardPaths, Qt,
                          pyqtSlot, pyqtSignal, QObject, QThread, QModelIndex, QEvent)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QDialog, QListWidgetItem,
                             QMessageBox, QItemDelegate, QLineEdit, QListWidget,
                             QFormLayout, QSpinBox, QDialogButtonBox)
                             
from PyQt6.QtGui import QColorConstants, QValidator, QFont, QTextCursor
from threading import Event
from importlib.resources import files
from pathlib import Path
from utils import all_files_newer
from solver import GuessManager, Color, DecisionTreeGuessManager
import shutil
import re
from tree_utils import routes_to_text

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

wordlesmash_ui_py_path = pathhelper('WordLeSmash_ui.py')
preferences_ui_py_path = pathhelper('preferences_ui.py')
newprofile_ui_py_path = pathhelper('NewProfile_ui.py')
batchadd_ui_py_path = pathhelper('BatchAdd_ui.py')

wordlesmash_rc_py_path = pathhelper('wordlesmash_rc.py')


from ui.wordlesmash_rc import qInitResources
qInitResources()

# if ANY .ui file is newer than any generated .py file, prefer compiling the UI.
# I.E. ONLY use generated files if they are newer

ui_paths = [wordlesmash_ui_path, preferences_ui_path, newprofile_ui_path,
            batchadd_ui_path]

ui_py_paths = [wordlesmash_ui_py_path, preferences_ui_py_path,
               newprofile_ui_py_path, batchadd_ui_py_path]

match all_files_newer(ui_paths, ui_py_paths):

    case True:
        logging.debug('importing ui files')
        from PyQt6 import uic
        # Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path, from_imports=True, import_from='ui')
        Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path)
        Ui_preferences, _ = uic.loadUiType(preferences_ui_path)
        Ui_NewProfile, _ = uic.loadUiType(newprofile_ui_path)
        Ui_BatchAdd, _ = uic.loadUiType(batchadd_ui_path)
    case False:
        logging.debug('importing generated files')
        from ui.WordLeSmash_ui import Ui_MainWindow
        from ui.preferences_ui import Ui_preferences
        from ui.NewProfile_ui import Ui_NewProfile
        from ui.BatchAdd_ui import Ui_BatchAdd
    case _:
        logging.critical('UI imports unavailable, exiting...')
        sys.exit(-1)

class ProfileManager:
    def __init__(self, parent=None, settings=None):
        self.settings = settings if settings is not None else QSettings()
        self.app_data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.app_cache_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        self.current_profile = None

    def getCurrentProfile(self):

        if not self.current_profile:
            return self.settings.value("default_profile", "Basic", type=str)
        else:
            return self.current_profile


    def setCurrentProfile(self, profile):
        self.current_profile = profile

    def setCurrentProfile(self, profile):
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

        self.waitingSpinner.setRoundness(70)
        self.waitingSpinner.setMinimumTrailOpacity(15)
        self.waitingSpinner.setTrailFadePercentage(70)
        self.waitingSpinner.setNumberOfLines(12)
        self.waitingSpinner.setLineLength(10)
        self.waitingSpinner.setLineWidth(5)
        self.waitingSpinner.setInnerRadius(10)
        self.waitingSpinner.setRevolutionsPerSecond(1)
        self.waitingSpinner.setColor(QColorConstants.Gray)


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
        # if (picks, candidates) != (None, None):
        self.picks, self.strategic_picks, self.candidates = suggestions
        # else:
        #     ... # None indicates search was aborted maybe, or an error
        self.ready.emit()

    def stop(self):
        self._stop_event.set()

class DecisionTreeRoutesGetter(QThread):
    ready = pyqtSignal(str, bool)  # Emits pick and success flag
    def __init__(self, profile_manager, pick, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.pick = pick
        self.app_cache_path = profile_manager.app_cache_path
        self.routes = []
        self._stop_event = Event()
        self.routes = []

    def run(self):
        try:
            guess_manager = DecisionTreeGuessManager(
                self.profile_manager.getPicks(),
                self.profile_manager.getCandidates(),
                length=self.profile_manager.getWordLength(),
                cache_path=self.app_cache_path
            )
            self.routes = guess_manager.gen_routes(self.pick)
            profile_name = self.profile_manager.getCurrentProfile()
            profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile_name
            dtree_dir = profile_dir / "dtree"
            dtree_dir.mkdir(parents=True, exist_ok=True)
            tree_file = dtree_dir / f"{self.pick}.txt"
            with tree_file.open("w", encoding="utf-8") as f: # would append mode fix?
                f.write(routes_to_text(self.routes))
            logging.debug(f"Decision tree saved to {tree_file}")
            self.ready.emit(self.pick, True)
        except Exception as e:
            logging.error(f"Failed to generate decision tree for {self.pick}: {e}")
            self.ready.emit(self.pick, False)

    def stop(self):
        self._stop_event.set()


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
        self._loading_settings = False  # Flag to prevent recursive loadProfileSettings
        self.initUI()
    
    def initUI(self):
        self.setupUi(self)
        logging.debug(f"initUI: QComboBox item count before clear: {self.profileComboBox.count()}")
        self.profileComboBox.clear()
        logging.debug(f"initUI: QComboBox item count after clear: {self.profileComboBox.count()}")
        self.profileComboBox.setEditable(True)
        self.profileComboBox.lineEdit().returnPressed.connect(self.renameProfile)
        self.profileComboBox.lineEdit().installEventFilter(self)
        self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
        # Connect dialog buttons (OK/Cancel)
        self.buttonBox.accepted.connect(self.saveSettings)
        # Connect add buttons to add new items and enter edit mode
        self.addInitialPickButton.clicked.connect(self.addInitialPick)
        self.addPickButton.clicked.connect(self.addPick)
        self.addCandidateButton.clicked.connect(self.addCandidate)
        self.removeInitialPickButton.clicked.connect(self.removeInitialPick)
        self.removePickButton.clicked.connect(self.removePick)
        self.removeCandidateButton.clicked.connect(self.removeCandidate)
        self.addProfileButton.clicked.connect(self.addProfile)
        self.removeProfileButton.clicked.connect(self.removeProfile)
        self.setDefaultProfileButton.clicked.connect(self.setDefaultProfile)

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
        # Connect selection change signal for initialPicksList
        self.initialPicksList.itemSelectionChanged.connect(self.onInitialPicksListSelectionChanged)
        # Connect chartTreeButton click to generate decision tree
        self.chartTreeButton.clicked.connect(self.onChartTreeButtonClicked)
        self.loadSettings()

    def eventFilter(self, watched, event):
        if watched == self.profileComboBox.lineEdit() and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.renameProfile()
                return True  # Consume the event to prevent dialog closure
        return super().eventFilter(watched, event)

    def updateCountLabels(self):
        """Update candidateCountLabel and picksCountLabel with current counts."""
        candidates_count = self.candidatesList.count()
        picks_count = self.picksList.count()
        self.candidatesCountLabel.setText(f"({candidates_count})")
        self.picksCountLabel.setText(f"({picks_count})")
        logging.debug(f"Updated labels: Candidates ({candidates_count}), Picks ({picks_count})")

    def getUniqueProfileName(self, base_name):
        """Generate a unique profile name by appending (N) if necessary."""
        profiles = [self.profileComboBox.itemText(i).rstrip(" *") for i in range(self.profileComboBox.count())]
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
        self.parent().guess
        selected_items = self.initialPicksList.selectedItems()
        if not selected_items:
            logging.debug("No word selected for decision tree generation")
            return
        pick = selected_items[0].text()
        profile_name = self.profileComboBox.currentText().rstrip(" *")
        logging.debug(f"Generating decision tree for word: {pick} in profile: {profile_name}")
        self.spawnDecisionTreeRoutesGetter(pick)
        
    @pyqtSlot(str, bool)
    def updateDecisionTrees(self):
        parent = self.parent()
        sender = self.sender() # the getter
        pick = sender.pick
        success = True
        self.waitingSpinner.stop()
        self.stopButton.setDisabled(True)
        try:
            parent.stopButton.clicked.disconnect()
        except TypeError:
            pass  # Signal not connected
        self.chartTreeButton.setEnabled(True)
        if success:
            parent.statusBar.showMessage(f"Decision tree generated for {pick}")
            # Add to decisionTreeList if not already present
            if pick not in [self.decisionTreeList.item(i).text() for i in range(self.decisionTreeList.count())]:
                self.decisionTreeList.addItem(pick)
            # Remove from initialPicksList
            for i in range(self.initialPicksList.count()):
                if self.initialPicksList.item(i).text() == pick:
                    self.initialPicksList.takeItem(i)
                    break
            self.saveSettings()  # Save updated initialPicksList
        else:
            parent.statusBar.showMessage(f"Failed to generate decision tree for {pick}")
            QMessageBox.warning(self, "Error", f"Failed to generate decision tree for '{pick}'")


        
    def loadSettings(self):
        logging.debug("Loading settings")
        self.profile_manager.settings.beginGroup("profiles")
        profiles = self.profile_manager.settings.childGroups()
        self.profile_manager.settings.endGroup()
        self.profileComboBox.clear()
        if not profiles:
            profiles = ["Basic"]
        default_profile = self.profile_manager.getCurrentProfile()
        logging.debug(f"Profiles: {profiles}, Default: {default_profile}")
        # Disconnect signals to prevent spurious triggers
        try:
            self.profileComboBox.currentTextChanged.disconnect(self.loadProfileSettings)
        except TypeError:
            pass  # Signal not connected
        try:
            for profile in profiles:
                display_text = f"{profile} *" if profile == default_profile else profile
                self.profileComboBox.addItem(display_text)
                self.profileComboBox.setItemData(self.profileComboBox.count() - 1, profile, Qt.ItemDataRole.UserRole)
                logging.debug(f"Added profile {profile} to QComboBox at index {self.profileComboBox.count() - 1}")
            index = self.profileComboBox.findText(f"{default_profile} *") if default_profile in profiles else self.profileComboBox.findText(default_profile)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
            else:
                self.profileComboBox.setCurrentIndex(0)
            # Sync ProfileManager with initial combo box selection
            selected_profile = self.profileComboBox.currentText().rstrip(" *")
            self.profile_manager.setCurrentProfile(selected_profile)
        finally:
            # Reconnect signals
            self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
        self.loadProfileSettings()

    @pyqtSlot(str)
    def loadProfileSettings(self, profile_name=None):
        if hasattr(self, '_loading_settings') and self._loading_settings:
            logging.debug(f"Skipping loadProfileSettings for {profile_name} due to recursive call")
            return
        self._loading_settings = True
        try:
            if profile_name:
                profile_name = profile_name.rstrip(" *")
            if not profile_name:
                profile_name = self.profileComboBox.currentText().rstrip(" *")
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
                    for pick in legal_picks:
                        self.picksList.addItem(pick)
            candidates_file = self.profile_manager.getCandidates()
            self.candidatesList.clear()
            if candidates_file.exists():
                with candidates_file.open("r", encoding="utf-8") as f:
                    candidates = [line.strip().upper() for line in f if line.strip()]
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
        finally:
            self._loading_settings = False

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
    def setDefaultProfile(self):
        profile_name = self.profileComboBox.currentText().rstrip(" *")
        if profile_name == self.profile_manager.getCurrentProfile(combo_box=self.profileComboBox):
            logging.debug(f"Profile {profile_name} is already default, skipping")
            return
        self.profile_manager.setCurrentProfile(profile_name)
        current_index = self.profileComboBox.currentIndex()
        self.profileComboBox.clear()
        logging.debug(f"QComboBox item count after clear in setDefaultProfile: {self.profileComboBox.count()}")
        self.profile_manager.settings.beginGroup("profiles")
        profiles = self.profile_manager.settings.childGroups()
        self.profile_manager.settings.endGroup()
        default_profile = self.profile_manager.getCurrentProfile()
        logging.debug(f"Setting default profile to {profile_name}, reloading QComboBox")
        for profile in profiles:
            display_text = f"{profile} *" if profile == default_profile else profile
            self.profileComboBox.addItem(display_text)
            self.profileComboBox.setItemData(self.profileComboBox.count() - 1, profile, Qt.ItemDataRole.UserRole)
            logging.debug(f"Added profile {profile} to QComboBox at index {self.profileComboBox.count() - 1}")
        self.profileComboBox.setCurrentIndex(current_index)

    @pyqtSlot()
    def renameProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            return
        old_name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole) or self.profileComboBox.itemText(current_index).rstrip(" *")
        new_name = self.profileComboBox.lineEdit().text().strip()
        logging.debug(f"Attempting to rename profile from {old_name} to {new_name}")
        if new_name == old_name or not new_name:
            self.profileComboBox.lineEdit().clear()
            return
        # Generate unique name if conflict
        new_name = self.getUniqueProfileName(new_name)
        self.profile_manager.settings.beginGroup(f"profiles/{old_name}")
        keys = self.profile_manager.settings.allKeys()
        values = [self.profile_manager.settings.value(key) for key in keys]
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.beginGroup(f"profiles/{new_name}")
        for key, value in zip(keys, values):
            self.profile_manager.settings.setValue(key, value)
        self.profile_manager.settings.endGroup()
        self.profile_manager.settings.beginGroup("profiles")
        self.profile_manager.settings.remove(old_name)
        self.profile_manager.settings.endGroup()
        if self.profile_manager.getCurrentProfile() == old_name:
            self.profile_manager.setCurrentProfile(new_name)
        old_dir = Path(self.profile_manager.app_data_path) / "profiles" / old_name
        new_dir = Path(self.profile_manager.app_data_path) / "profiles" / new_name
        if old_dir.exists():
            old_dir.rename(new_dir)
        default_profile = self.profile_manager.getCurrentProfile()
        display_text = f"{new_name} *" if new_name == default_profile else new_name
        self.profileComboBox.setItemText(current_index, display_text)
        self.profileComboBox.setItemData(current_index, new_name, Qt.ItemDataRole.UserRole)
        logging.debug(f"Renamed profile to {new_name}, reloading settings")
        self.profileComboBox.lineEdit().clear()
        self.loadProfileSettings(new_name)

    @pyqtSlot()
    def removeProfile(self):
        profile_name = self.profileComboBox.currentText().rstrip(" *")
        if profile_name.startswith("Basic"):
            QMessageBox.warning(self, "Cannot Delete", "Profiles starting with 'Basic' cannot be deleted.")
            return
        reply = QMessageBox.question(self, "Delete Profile", f"Delete profile '{profile_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logging.debug(f"Removing profile: {profile_name}")
            self.profile_manager.settings.beginGroup("profiles")
            self.profile_manager.settings.remove(profile_name)
            self.profile_manager.settings.endGroup()
            profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile_name
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
            current_index = self.profileComboBox.currentIndex()
            self.profileComboBox.removeItem(current_index)
            if self.profileComboBox.count() > 0:
                self.profileComboBox.setCurrentIndex(0)
                new_profile = self.profileComboBox.currentText().rstrip(" *")
                self.profile_manager.setCurrentProfile(new_profile)
            else:
                self.profileComboBox.addItem("Basic")
                self.profileComboBox.setItemData(0, "Basic", Qt.ItemDataRole.UserRole)
                self.profile_manager.setCurrentProfile("Basic")
                self.profileComboBox.setCurrentIndex(0)
            logging.debug(f"QComboBox contents after removeProfile: {[self.profileComboBox.itemText(i) for i in range(self.profileComboBox.count())]}")
            self.loadProfileSettings()

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
            word = self.picksList.item(current_row).text()
            self.picksList.takeItem(current_row)
            # Remove from candidatesList to maintain candidates ⊆ picks
            for i in range(self.candidatesList.count()):
                if self.candidatesList.item(i).text() == word:
                    self.candidatesList.takeItem(i)
                    break
            self.savePicksToFile()
            self.saveSettings()
            self.updateCountLabels()

    @pyqtSlot()
    def savePicksToFile(self):
        """Save picksList to picks.txt."""
        profile_name = self.profileComboBox.currentText().rstrip(" *")
        profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        picks_file = profile_dir / "picks.txt"
        legal_picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        with picks_file.open("w", encoding="utf-8") as f:
            for pick in legal_picks:
                if pick.strip():
                    f.write(pick + "\n")

    @pyqtSlot()
    def addInitialPick(self):
        """Add a new item to initialPicksList and enter edit mode."""
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addInitialPickButton.setDisabled(True)
        self.initialPicksList.addItem(new_item)
        self.initialPicksList.scrollToBottom()
        self.initialPicksList.setCurrentItem(new_item)
        self.initialPicksList.setFocus()
        try:
            self.initialPicksList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for initialPicksList: {e}")

    @pyqtSlot()
    def addPick(self):
        """Add a new item to picksList and enter edit mode."""
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        
        self.addPickButton.setDisabled(True)
        self.picksList.addItem(new_item)
        self.picksList.scrollToBottom()
        self.picksList.setCurrentItem(new_item)
        self.picksList.setFocus()
        try:
            self.picksList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for picksList: {e}")
        self.updateCountLabels()

    @pyqtSlot()
    def addCandidate(self):
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addCandidateButton.setDisabled(True)
        self.candidatesList.addItem(new_item)
        self.candidatesList.scrollToBottom()
        self.candidatesList.setCurrentItem(new_item)
        self.candidatesList.setFocus()
        try:
            self.candidatesList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for candidatesList: {e}")
        self.updateCountLabels()

    @pyqtSlot()
    def removeInitialPick(self):
        current_row = self.initialPicksList.currentRow()
        if current_row >= 0:
            self.initialPicksList.takeItem(current_row)
            self.saveSettings()

    @pyqtSlot()
    def removeCandidate(self):
        current_row = self.candidatesList.currentRow()
        if current_row >= 0:
            self.candidatesList.takeItem(current_row)
            self.saveSettings()
            self.updateCountLabels()

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
            default_profile = self.profile_manager.getCurrentProfile()
            try:
                self.profileComboBox.currentTextChanged.disconnect(self.loadProfileSettings)
            except TypeError:
                pass
            try:
                self.profileComboBox.addItem(name if name != default_profile else f"{name} *")
                self.profileComboBox.setItemData(self.profileComboBox.count() - 1, name, Qt.ItemDataRole.UserRole)
                self.profileComboBox.setCurrentIndex(self.profileComboBox.count() - 1)
                logging.debug(f"Added profile {name} to QComboBox at index {self.profileComboBox.count() - 1}")
                self.profile_manager.setCurrentProfile(name)
            finally:
                self.profileComboBox.currentTextChanged.connect(self.loadProfileSettings)
            self.loadProfileSettings(name)

    @pyqtSlot()
    def saveSettings(self):
        """Save the current profile settings and default profile to QSettings and data files."""
        profile_name = self.profileComboBox.currentText().rstrip(" *")
        logging.debug(f"Saving settings for profile {profile_name}")
        self.profile_manager.settings.beginGroup(f"profiles/{profile_name}")
        old_game_type = self.profile_manager.settings.value("game_type", "wordle", type=str)
        new_game_type = self.gameTypeComboBox.currentText()
        game_type_changed = old_game_type != new_game_type
        self.profile_manager.settings.setValue("game_type", new_game_type)
        self.profile_manager.settings.setValue("word_length", self.word_length)
        initial_picks = [self.initialPicksList.item(i).text() for i in range(self.initialPicksList.count())]
        self.profile_manager.settings.setValue("initial_picks", "\n".join([pick for pick in initial_picks if pick.strip()]))
        self.profile_manager.settings.endGroup()
        profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)
        picks_file = Path(profile_dir / "picks.txt")
        # Check if picks have changed
        old_picks = set()
        if picks_file.exists():
            with picks_file.open("r", encoding="utf-8") as f:
                old_picks = {line.strip().upper() for line in f if line.strip()}
        legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count()) if self.picksList.item(i).text().strip()}
        picks_changed = old_picks != legal_picks
        with picks_file.open("w", encoding="utf-8") as f:
            for pick in legal_picks:
                if pick.strip():
                    f.write(pick + "\n")
        candidates_file = Path(profile_dir / "candidates.txt")
        # Check if candidates have changed
        old_candidates = set()
        if candidates_file.exists():
            with candidates_file.open("r", encoding="utf-8") as f:
                old_candidates = {line.strip().upper() for line in f if line.strip()}
        solution_candidates = {self.candidatesList.item(i).text() for i in range(self.candidatesList.count()) if self.candidatesList.item(i).text().strip()}
        candidates_changed = old_candidates != solution_candidates
        with candidates_file.open("w", encoding="utf-8") as f:
            for candidate in solution_candidates:
                if candidate.strip():
                    f.write(candidate + "\n")
        # Unlink decision tree files only if picks, candidates, or game_type changed
        dtree_dir = profile_dir / "dtree"
        dtree_dir.mkdir(parents=True, exist_ok=True)
        if game_type_changed or picks_changed or candidates_changed:
            logging.debug(f"Decision tree invalidation triggered: game_type_changed={game_type_changed}, picks_changed={picks_changed}, candidates_changed={candidates_changed}")
            # Collect deleted tree words to add back to initialPicksList
            deleted_picks = []
            for file_path in dtree_dir.glob("*.txt"):
                deleted_picks.append(file_path.stem)
                file_path.unlink()
            # Clear decisionTreeList
            self.decisionTreeList.clear()
            # Add deleted picks to initialPicksList, avoiding duplicates
            current_initial_picks = {self.initialPicksList.item(i).text() for i in range(self.initialPicksList.count())}
            for pick in deleted_picks:
                if pick and pick not in current_initial_picks:
                    self.initialPicksList.addItem(pick)
            logging.debug(f"Added deleted picks back to initialPicksList: {deleted_picks}")
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
        getter.start()

    def spawnDecisionTreeRoutesGetter(self, pick):
        parent = self.parent()

        parent.statusBar.showMessage(f"Generating decision tree for {pick}...")

        # Create a thread that will launch a search
        self.chartTreeButton.setDisabled(True)
        # self.statusBar.showMessage('Generating picks...')
        self.waitingSpinner.start()

        # might not need to regenerate this every time

        self.guess = DecisionTreeGuessManager(self.profile_manager.getPicks(),
                                            self.profile_manager.getCandidates(),
                                            length=self.profile_manager.getWordLength(),
                                            cache_path=self.profile_manager.app_cache_path)

        getter = DecisionTreeRoutesGetter(self.profile_manager, pick, self)
        self.stopButton.clicked.connect(getter.stop)
        self.stopButton.setEnabled(True)
        getter.ready.connect(self.updateDecisionTrees)
        getter.start()

    # def updateDecisionTrees(self):

    #     sender = self.sender() # the getter
    #     pick = sender.pick
    #     self.waitingSpinner.stop()  
    #     self.stopButton.setDisabled(True)
    #     self.stopButton.clicked.disconnect()
    #     self.

    #     # profile_name = self.profile_manager.getCurrentProfile()

    #     # if isinstance(sender, DecisionTreeRoutesGetter):
    #     #     routes = sender.routes
    #     #     pick = sender.pick
    #     # else:
    #     #     logging.debug(type(sender))

    #     # profile_dir = Path(self.profile_manager.app_data_path) / "profiles" / profile_name

    #     # dtree_dir = profile_dir / "dtree"

    #     # if routes:
    #     #     
    #     #     with open(dtree_dir / (pick + '.txt'), 'w') as f:
    #     #         f.write(routes_to_text(routes))
    #     #         pass



        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = MainWordLeSmashWindow()
    main.show()
    sys.exit(app.exec())
