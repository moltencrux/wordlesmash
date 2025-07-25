#!/usr/bin/env -S python3 -O
import logging, sys, os
from PyQt6.QtCore import (QCoreApplication, QSettings, Qt, pyqtSlot, pyqtSignal,
                          QObject, QThread)

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QColorConstants
from threading import Event
from importlib.resources import files
from pathlib import Path
from utils import all_files_newer
from solver import GuessManager, Color, DecisionTreeGuessManager

QCoreApplication.setApplicationName('moltencrux')
QCoreApplication.setOrganizationName('WordLeSmash')
settings = QSettings()

# Only log debug level messages in debug mode
if __debug__:
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    logging.debug('debug mode on')
else:
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR)


def pathhelper(resource, package='ui'):
    return Path(files(package) / resource)


wordlesmash_ui_path = pathhelper('WordLeSmash.ui')
wordlesmash_ui_py_path = pathhelper('WordLeSmash_ui.py')

# if ANY .ui file is newer than any generated .py file, prefer compiling the UI.
# I.E. ONLY use generated files if they are newer
match all_files_newer([wordlesmash_ui_path], [wordlesmash_ui_py_path]):
    case True:
        logging.debug('importing ui files')
        from PyQt6 import uic
        # Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path, from_imports=True, import_from='ui')
        Ui_MainWindow, _ = uic.loadUiType(wordlesmash_ui_path)
    case False:
        logging.debug('importing generated files')
        from ui.WordLeSmash_ui import Ui_MainWindow
        # from ui.settings_ui import Ui_settings
    case _:
        logging.critical('UI imports unavailable, exiting...')
        sys.exit(-1)


class MainWordLeSmashWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        # FormulaList.setSettings(self.settings) I don't think this is necessary
        self.initUI()

        print(f'{type(self.waitingSpinner) = }')
        self.setSpinnerProperties()
        # self.guess = GuessManager(filename='default_words.txt', length=5)
        self.guess = DecisionTreeGuessManager('wordle_picks.txt',
                                              'wordle_candidates.txt',
                                              'dtree/output_dt_rance.5.txt')

        self.onWordSubmitted()

        self.guessDisplay.wordSubmitted.connect(self.onWordSubmitted)
        self.guessDisplay.wordWithdrawn.connect(self.onWordWithdrawn)
        self.resetButton.clicked.connect(self.onResetGame)
        self.stopButton.setDisabled(True)
        self.stopButton.clicked.connect(self.onCancelSearch)


        #self.key_ENTER.setStyleSheet("background-color: red; color: white; :disabled {background-color: gray; color: black;} :enabled {background-color: green; color: white;}")
        # self.key_ENTER.setStyleSheet(":disabled {background-color: gray; color: darkgray;} :enabled {background-color: green; color: white;}")

        self.key_A.setStyleSheet("""
            QPushButton {
                background-color: #ffa500;
                border: 5px solid #15cb1b;
                border-style: solid;
                border-radius: 5px
            }
        """)
        
        self.guessDisplay.set_color_callback(self.guess.get_allowed_colors_by_slot)


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
            for c in candidates:
                self.solutionListWidget.addItem(c)

        if self.solutionListWidget.count() > 1:
            self.guessDisplay.setSubmitEnabled(True)
            self.key_ENTER.setEnabled(True)

        self.guessDisplay.setWithdrawEnabled(True)


    @pyqtSlot(str, tuple)
    def onWordSubmitted(self, word=None, colors=None):
        """Slot to handle wordSubmitted signal."""

        self.guess.update_guess_result(word, colors)


        print(f"Received wordSubmitted: '{word} {colors}'")

        self.spawnSuggestionGetter()


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


    def initUI(self):
        self.setupUi(self)
        self.guessDisplay.setFocus()


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


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = MainWordLeSmashWindow()
    main.show()
    sys.exit(app.exec())
