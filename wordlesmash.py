#!/usr/bin/env -S python3 -O
import logging, sys, os
from PyQt6.QtCore import (QCoreApplication, QSettings, Qt, pyqtSlot, pyqtSignal,
                          QObject, QThread)

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QColorConstants
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


    # @pyqtSlot why is this broken?
    def updateSuggestionLists(self):
        """This should be called when the suggestions are ready"""

        self.waitingSpinner.stop()
        self.statusBar.showMessage('Suggestions ready!')
        sender = self.sender()

        if isinstance(sender, SuggestionGetter):
            picks = sender.picks
            candidates = sender.candidates
        else:
            logging.debug(type(sender))

        self.strategicListWidget.clear()
        for s in picks:
            self.strategicListWidget.addItem(s)


        self.solutionListWidget.clear()
        for c in candidates:
            self.solutionListWidget.addItem(c)

        self.guessDisplay.setSubmitEnabled(True)
        self.key_ENTER.setEnabled(True)


    # @pyqtSlot wtf?
    def onWordSubmitted(self, word=None, colors_hex=None):
        """Slot to handle wordSubmitted signal."""

        self.guessDisplay.setSubmitDisabled(True)
        self.waitingSpinner.start()
        self.key_ENTER.setDisabled(True)

        if word is not None and colors_hex is not None:

            color_map = {'#000000': Color.BLACK, '#6aaa64': Color.GREEN, "#c9b458": Color.YELLOW}

            colors = tuple(color_map.get(c, Color.UNKNOWN) for c in colors_hex)
        else:
            word = None
            colors = None

        print(f"Received wordSubmitted: '{word} {colors}'")

        self.guess.update_guess_result(word, colors)
        self.spawnSuggestionGetter()


    def spawnSuggestionGetter(self):

        # Create a thread that will launch a search
        getter = SuggestionGetter(self)
        getter.finished.connect(self.updateSuggestionLists)
        getter.start()
        self.statusBar.showMessage('Rebuilding decision tree...')


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

    def run(self):
        self.picks, self.candidates = self.parent().guess.get_suggestions()
        self.ready.emit()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = MainWordLeSmashWindow()
    main.show()
    sys.exit(app.exec())
