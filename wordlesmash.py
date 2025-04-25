#!/usr/bin/env -S python3 -O
import logging, sys, os
from PyQt6.QtCore import QCoreApplication, QSettings, Qt, pyqtSlot, pyqtSignal

from PyQt6.QtWidgets import QApplication, QMainWindow

from importlib.resources import files
from pathlib import Path
from utils import all_files_newer
from solver import GuessManager, Color

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

        self.guess = GuessManager(filename='default_words.txt', length=5)
        self.updateSuggestionLists()
        # hook stuff up
        # what is the connect signall?

        self.guessDisplay.wordSubmitted.connect(self.onWordSubmitted)
        self.guessDisplay.wordWithdrawn.connect(self.onWordWithdrawn)
        self.resetButton.clicked.connect(self.onResetGame)

    def updateSuggestionLists(self):

        result = self.guess.get_suggestions()
        strategic = result['narrowers']
        answers = result['candidates']

        self.strategicListWidget.clear()
        for s in strategic:
            self.strategicListWidget.addItem(s)


        self.solutionListWidget.clear()
        for s in answers:
            self.solutionListWidget.addItem(s)


    def onWordSubmitted(self, word, colors_hex):
        """Slot to handle wordSubmitted signal."""

        color_map = {'#000000': Color.BLACK, '#6aaa64': Color.GREEN, "#c9b458": Color.YELLOW}

        colors = [color_map.get(c, Color.UNKNOWN) for c in colors_hex]

        print(f"Received wordSubmitted: '{word} {colors}'")

        self.guess.update_guess_result(word, colors)
        self.updateSuggestionLists()

    @pyqtSlot()
    def onWordWithdrawn(self):
        print('onWordWithdrawn called')
        self.guess.undo_last_guess()
        self.updateSuggestionLists()

    @pyqtSlot()
    def onResetGame(self):
        print('onResetGame called')
        self.guessDisplay.clear()
        self.guess.reset()
        self.updateSuggestionLists()


    def initUI(self):
        self.setupUi(self)
        self.guessDisplay.setFocus()



    def _on_load_finished(self):
        ...



if __name__ == '__main__':
    app = QApplication(sys.argv)
    main = MainWordLeSmashWindow()
    main.show()
    sys.exit(app.exec())
