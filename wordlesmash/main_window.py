from PyQt6.QtCore import pyqtSlot, QSettings
from PyQt6.QtWidgets import QMainWindow
from typing import List, Tuple
from .ui_loader import load_ui_class, UI_CLASSES
from .ui.wordlesmash_rc import qInitResources
from .preferences import MainPreferences
from .profile_manager import ProfileManager
from .solver import DecisionTreeGuessManager
from .dialogs import ProgressDialog
from .workers import SuggestionGetter, DecisionTreeRoutesGetter
import logging

logger = logging.getLogger(__name__)

Ui_MainWindow = load_ui_class(*UI_CLASSES['MainWordLeSmashWindow'])

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
        dt = self.profile_manager.getDecisionTrees()
        self.guess = DecisionTreeGuessManager(
            self.profile_manager.getPicks(),
            self.profile_manager.getCandidates(),
            dt,
            length=self.profile_manager.getWordLength(),
            cache_path=self.profile_manager.app_cache_path()
        )
        if not dt:
            self.spawnInitialTreeRoutesGetter()
        else:
            self.onWordSubmitted()

    @pyqtSlot()
    def updateSuggestionLists(self):
        """This should be called when the suggestions are ready"""

        self.statusBar.showMessage('Suggestions ready!')
        sender = self.sender()

        if isinstance(sender, SuggestionGetter):
            picks = sender.picks
            contingency_solutions = sender.strategic_picks
            candidates = sender.candidates
        else:
            candidates = []
            logging.debug(type(sender))
            logging.debug("Empty or invalid routes generated")

        self.decisionTreeListWidget.clear()
        self.contingencyListWidget.clear()
        self.solutionListWidget.clear()
        self.solutionCountLabel.setText(f'({len(candidates)})')
        if candidates:
            self.decisionTreeListWidget.addItems(picks)
            self.contingencyListWidget.addItems(contingency_solutions)
            self.solutionListWidget.addItems(candidates)
        if self.solutionListWidget.count() > 1:
            self.guessDisplay.setSubmitEnabled(True)
            # self.key_ENTER.setEnabled(True)

        self.guessDisplay.setWithdrawEnabled(True)
        self.setEnabled(True)

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
        getter.finished.connect(self.guessDisplay.setFocus)

        self.setDisabled(True)
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

    def spawnInitialTreeRoutesGetter(self):
        """Start a DecisionTreeRoutesGetter thread to generate a near-otpimal
        full root-to-leaf decision tree."""
        
        parent = self.parent()

        # Create a thread that will launch a search
        self.setDisabled(True)

        getter = DecisionTreeRoutesGetter(self.profile_manager, None, self.guess, self)
        progress_dialog = ProgressDialog(self, cancel_callback=getter.stop)
        getter.ready.connect(self.updateInitialDecisionTree)
        getter.finished.connect(progress_dialog.close)
        getter.finished.connect(self.guessDisplay.setFocus)
        progress_dialog.show()
        getter.start()

    def updateInitialDecisionTree(self, name: str, routes: List[Tuple[str]], success: bool):
        """Add or update a decision tree in a profile."""
        if success:
            name = self.profile_manager.getCurrentProfileName()
            self.profile_manager.addDecisionTree(name, routes, success)
            self.profile_manager.commitChanges()
            self.resetGuessManager()
            self.setEnabled(True)
