#!/usr/bin/env -S python3 -O
import logging, sys, os
from PyQt6.QtCore import (QCoreApplication, QSettings, QStandardPaths, Qt,
                          pyqtSlot, pyqtSignal, QObject, QThread)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QDialog, QListWidgetItem,
                             QMessageBox, QItemDelegate, QLineEdit, QListWidget,
                             QFormLayout, QSpinBox, QDialogButtonBox)
                             
from PyQt6.QtGui import QColorConstants, QValidator, QFont
from threading import Event
from importlib.resources import files
from pathlib import Path
from utils import all_files_newer
from solver import GuessManager, Color, DecisionTreeGuessManager

QCoreApplication.setApplicationName('WordLeSmash')
QCoreApplication.setOrganizationName('moltencrux')




# # Get the standard location for application data
# config_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
# 
# # Ensure the directory exists
# os.makedirs(config_dir, exist_ok=True)
# 
# # Define the path for your config file
# config_file_path = os.path.join(config_dir, 'config.json')


# Only log debug level messages in debug mode
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

wordlesmash_ui_py_path = pathhelper('WordLeSmash_ui.py')
preferences_ui_py_path = pathhelper('preferences_ui.py')
newprofile_ui_py_path = pathhelper('NewProfile_ui.py')
wordlesmash_rc_py_path = pathhelper('wordlesmash_rc.py')


# if ANY .ui file is newer than any generated .py file, prefer compiling the UI.
# I.E. ONLY use generated files if they are newer

from ui.wordlesmash_rc import qInitResources
qInitResources()

# wordlesmash_rc_py_path

match all_files_newer([wordlesmash_ui_path, preferences_ui_path, newprofile_ui_path],
                      [wordlesmash_ui_py_path, preferences_ui_py_path, newprofile_ui_py_path]):

    case True:
        logging.debug('importing ui files')
        from PyQt6 import uic
        # Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path, from_imports=True, import_from='ui')
        Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path)
        Ui_preferences, _ = uic.loadUiType(preferences_ui_path)
        Ui_NewProfile, _ = uic.loadUiType(newprofile_ui_path)
    case False:
        logging.debug('importing generated files')
        from ui.WordLeSmash_ui import Ui_MainWindow
        from ui.preferences_ui import Ui_preferences
        from ui.NewProfile_ui import Ui_NewProfile
    case _:
        logging.critical('UI imports unavailable, exiting...')
        sys.exit(-1)


class MainWordLeSmashWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        # FormulaList.setSettings(self.settings) I don't think this is necessary
        self.initUI()

    def getPicksFile(self):
        current_profile = self.getCurrentProfile()
        picks_file = Path(self.app_data_path) / "profiles" / current_profile / "picks.txt"
        return picks_file

    def getCandidatesFile(self):
        current_profile = self.getCurrentProfile()
        candidates_file = Path(self.app_data_path) / "profiles" / current_profile / "candidates.txt"
        return candidates_file

        # self.settings.beginGroup(f"profiles/{profile_name}")
        # profiles = self.settings.childGroups()
        # self.settings.endGroup()

    def getCurrentProfile(self):
        if not hasattr(self, '_current_profile'):
            self._current_profile =  self.settings.value("default_profile", "default", type=str)

        return self._current_profile

    def setCurrentProfile(self, profile):
        self._current_profile = profile

    def getWordLength(self):
        # Access profile settings under profiles/<profile_name>
        self.settings.beginGroup(f"profiles/{self.getCurrentProfile()}")
        word_length = self.settings.value("word_length", 5, type=int)
        self.settings.endGroup()
        return word_length



    def initUI(self):
        self.setupUi(self)
        self.settings = QSettings()
        self.app_data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.app_cache_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        self.guessDisplay.setFocus()

        print(f'{type(self.waitingSpinner) = }')
        self.setSpinnerProperties()
        # self.guess = GuessManager(filename='default_words.txt', length=5)
        self.getWordLength()
        self.guess = DecisionTreeGuessManager(self.getPicksFile(),
                                              self.getCandidatesFile(),
                                              'dtree/output_dt_rance.5.txt',
                                              length=self.getWordLength(),
                                              cache_path=self.app_cache_path)

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
            candidates = sender.candidates
        else:
            candidates = ()
            logging.debug(type(sender))

        if candidates:

            self.strategicListWidget.clear()
            for s in picks:
                self.strategicListWidget.addItem(s)

            self.solutionListWidget.clear()
            for c in sorted(candidates):
                self.solutionListWidget.addItem(c)

            self.solutionCountLabel.setText(str(len(candidates)))

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
        self.candidates = []
        self._stop_event = Event()

    def run(self):
        picks, candidates = self.parent().guess.get_suggestions()
        # if (picks, candidates) != (None, None):
        self.picks, self.candidates = picks, candidates
        # else:
        #     ... # None indicates search was aborted maybe, or an error
        self.ready.emit()

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

class MainPreferences(QDialog, Ui_preferences):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = parent.settings or QSettings()
        self.app_data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.word_length = 5  # Default word length
        self.initUI()
    
    def initUI(self):
        self.setupUi(self)
        # Connect profile selection change to update UI
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
        delegate_initial = UpperCaseDelegate(self.word_length, self.initialPicksList)
        delegate_initial.closeEditor.connect(self.onCloseInitPicksEditor)
        self.initialPicksList.setItemDelegate(delegate_initial)
        delegate_picks = UpperCaseDelegate(self.word_length, self.picksList)
        delegate_picks.closeEditor.connect(self.onClosePicksEditor)
        self.picksList.setItemDelegate(delegate_picks)
        delegate_candidates = UpperCaseDelegate(self.word_length, self.candidatesList)
        delegate_candidates.closeEditor.connect(self.onCloseCandidatesEditor)
        self.candidatesList.setItemDelegate(delegate_candidates)
        # self.wordLengthSpinBox.setReadOnly(True)  # Make word length fixed for existing profiles
        self.loadSettings()


    def loadSettings(self):
        """Load the default profile and populate the profile combo box with all profiles."""
        self.settings.beginGroup("profiles")
        profiles = self.settings.childGroups()
        self.settings.endGroup()

        self.profileComboBox.clear()
        if not profiles:
            profiles = ["default"]
        self.profileComboBox.addItems(profiles)

        default_profile = self.settings.value("default_profile", "default", type=str)
        index = self.profileComboBox.findText(default_profile)
        if index >= 0:
            self.profileComboBox.setCurrentIndex(index)
        else:
            self.profileComboBox.setCurrentIndex(0)

        self.loadProfileSettings()

    @pyqtSlot(str)
    def loadProfileSettings(self, profile_name=None):
        """Load settings for the specified profile (or current profile if None)."""
        if not profile_name:
            profile_name = self.profileComboBox.currentText()
        if not profile_name:
            profile_name = "default"

        self.settings.beginGroup(f"profiles/{profile_name}")

        game_type = self.settings.value("game_type", "wordle", type=str)
        self.gameTypeComboBox.setCurrentText(game_type)
        self.word_length = self.settings.value("word_length", 5, type=int)
        self.wordLengthDisplayLabel.setText(str(self.word_length))
        initial_picks = self.settings.value("initial_picks", "CRANE\nSLATE", type=str)
        self.initialPicksList.clear()
        if initial_picks:
            for pick in initial_picks.split("\n"):
                if pick.strip():
                    self.initialPicksList.addItem(pick.strip().upper())

        self.settings.endGroup()

        picks_file = Path(self.app_data_path) / "profiles" / profile_name / "picks.txt"
        self.picksList.clear()
        default_legal_picks = ["ABOUT", "AUDIO", "CRANE", "SLATE"]
        if picks_file.exists():
            with picks_file.open("r", encoding="utf-8") as f:
                legal_picks = [line.strip().upper() for line in f if line.strip()]
                for pick in legal_picks:
                    self.picksList.addItem(pick)
        else:
            for pick in default_legal_picks:
                self.picksList.addItem(pick.upper())
 
        candidates_file = Path(self.app_data_path) / "profiles" / profile_name / "candidates.txt"
        self.candidatesList.clear()
        default_solution_candidates = ["AUDIO", "CRANE"]
        if candidates_file.exists():
            with candidates_file.open("r", encoding="utf-8") as f:
                candidates = [line.strip().upper() for line in f if line.strip()]
                for candidate in candidates:
                    self.candidatesList.addItem(candidate)
        else:
            for candidate in default_solution_candidates:
                self.candidatesList.addItem(candidate.upper())

        dtree_dir = Path(self.app_data_path) / "profiles" / profile_name / "dtree"
        self.decisionTreeList.clear()
        default_trees = []
        if dtree_dir.exists():
            for file_path in dtree_dir.glob("*.txt"):
                self.decisionTreeList.addItem(file_path.stem)
        else:
            for tree in default_trees:
                self.decisionTreeList.addItem(tree)
        # Update delegates with new word length
        self.updateDelegates()

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
            else:
                self.initialPicksList.takeItem(self.initialPicksList.row(item))
                return

    @pyqtSlot(QListWidgetItem)
    def validatePick(self, item):
        """Validate and normalize the pick."""
        text = item.text().strip().upper()
        if not text:
            self.picksList.takeItem(self.picksList.row(item))
            return
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.picksList.takeItem(self.picksList.row(item))
            return

    @pyqtSlot(QListWidgetItem)
    def validateCandidate(self, item):
        """Validate and normalize the candidate, adding to picksList if valid."""
        text = item.text().strip().upper()
        if not text:
            self.candidatesList.takeItem(self.candidatesList.row(item))
            return
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.candidatesList.takeItem(self.candidatesList.row(item))
            return
        legal_picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        if text not in legal_picks:
            self.picksList.addItem(text)
            self.savePicksToFile()

    def savePicksToFile(self):
        """Save picksList to picks.txt."""
        profile_name = self.profileComboBox.currentText()
        profile_dir = Path(self.app_data_path) / "profiles" / profile_name
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
            print(f"Failed to enter edit mode for initialPicksList: {e}")

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
            print(f"Failed to enter edit mode for picksList: {e}")

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
            print(f"Failed to enter edit mode for candidatesList: {e}")

    @pyqtSlot()
    def removeInitialPick(self):
        current_row = self.initialPicksList.currentRow()
        if current_row >= 0:
            self.initialPicksList.takeItem(current_row)
            self.saveSettings()

    @pyqtSlot()
    def removePick(self):
        current_row = self.picksList.currentRow()
        if current_row >= 0:
            self.picksList.takeItem(current_row)
            self.savePicksToFile()

    @pyqtSlot()
    def removeCandidate(self):
        current_row = self.candidatesList.currentRow()
        if current_row >= 0:
            self.candidatesList.takeItem(current_row)
            self.saveSettings()

    @pyqtSlot()
    def addProfile(self):
        dialog = NewProfileDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.nameEdit.text().strip()
            length = dialog.lengthSpinBox.value()
            if self.profileComboBox.findText(name) >= 0:
                QMessageBox.warning(self, "Duplicate Name", "A profile with this name already exists.")
                return
            self.settings.beginGroup(f"profiles/{name}")
            self.settings.setValue("word_length", length)
            self.settings.setValue("game_type", "wordle")  # Default game type

            self.settings.endGroup()
            profile_dir = Path(self.app_data_path) / "profiles" / name
            profile_dir.mkdir(parents=True, exist_ok=True)
            # Create default picks and candidates files
            picks_file = profile_dir / "picks.txt"
            picks_file.touch()
            candidates_file = profile_dir / "candidates.txt"
            candidates_file.touch()

            self.profileComboBox.addItem(name)
            self.profileComboBox.setCurrentText(name)

    @pyqtSlot()
    def saveSettings(self):
        """Save the current profile settings and default profile to QSettings and data files."""
        profile_name = self.profileComboBox.currentText()
        # Save default profile
        self.settings.setValue("default_profile", profile_name)
        # Save profile-specific settings
        self.settings.beginGroup(f"profiles/{profile_name}")

        # Save game_type
        self.settings.setValue("game_type", self.gameTypeComboBox.currentText())
        self.settings.setValue("word_length", self.word_length)
        initial_picks = [self.initialPicksList.item(i).text() for i in range(self.initialPicksList.count())]
        self.settings.setValue("initial_picks", "\n".join([pick for pick in initial_picks if pick.strip()]))

        self.settings.endGroup()

        # Ensure profile directory exists
        profile_dir = Path(self.app_data_path) / "profiles" / profile_name
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Save legal picks to picks.txt
        picks_file = profile_dir / "picks.txt"
        legal_picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        with picks_file.open("w", encoding="utf-8") as f:
            for pick in legal_picks:
                if pick.strip():
                    f.write(pick + "\n")

        # Save solution candidates to candidates.txt
        candidates_file = profile_dir / "candidates.txt"
        solution_candidates = [self.candidatesList.item(i).text() for i in range(self.candidatesList.count())]
        with candidates_file.open("w", encoding="utf-8") as f:
            for candidate in solution_candidates:
                if candidate.strip():
                    f.write(candidate + "\n")

        # Save decision trees to dtree/ directory
        dtree_dir = profile_dir / "dtree"
        dtree_dir.mkdir(parents=True, exist_ok=True)
        # Clear existing .txt files in dtree/ to avoid stale files
        for file_path in dtree_dir.glob("*.txt"):
            file_path.unlink()
        # Save each decision tree as a .txt file
        for i in range(self.decisionTreeList.count()):
            tree_name = self.decisionTreeList.item(i).text()
            if tree_name.strip():
                tree_file = dtree_dir / f"{tree_name}.txt"
                tree_file.touch()

        # Sync settings to ensure QSettings are saved
        self.settings.sync()

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


        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = MainWordLeSmashWindow()
    main.show()
    sys.exit(app.exec())
