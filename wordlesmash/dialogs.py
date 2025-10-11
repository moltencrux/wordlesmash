from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtWidgets import QDialog, QMessageBox
from PyQt6.QtGui import QCloseEvent, QTextCursor
from .ui_loader import load_ui_class, UI_CLASSES
import logging
from itertools import cycle
import re

logger = logging.getLogger(__name__)

Ui_NewProfile = load_ui_class(*UI_CLASSES['NewProfileDialog'])
Ui_BatchAdd = load_ui_class(*UI_CLASSES['BatchAddDialog'])
Ui_ProgressDialog = load_ui_class(*UI_CLASSES['ProgressDialog'])


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
    def __init__(self, parent=None, words: list = None, word_length: int = 5, title: str = "Batch Add Words"):
        super().__init__(parent)
        self.words = words or []
        self.word_length = word_length
        self.initUI()
        self.setWindowTitle(title)

    def initUI(self):
        self.setupUi(self)
        self.addWordsEdit.extraContextActions.append(self.actionFormat)
        self.actionFormat.triggered.connect(self.formatText)

    def showEvent(self, event):
        super().showEvent(event)
        self.populateWords()

    def populateWords(self):
        self.addWordsEdit.clear()
        words = sorted(self.words)
        self.addWordsEdit.setPlainText('\n'.join(words))
        self.addWordsEdit.moveCursor(QTextCursor.MoveOperation.End)
        logger.debug(f"populateWords: Loaded {len(words)} words into addWordsEdit")

    def formatText(self):
        text = self.addWordsEdit.toPlainText()
        words = {word.upper() for word in re.findall(r'[a-zA-Z]+', text) if len(word) == self.word_length and word.isalpha()}
        new_text = '\n'.join(sorted(words)) + '\n'
        self.addWordsEdit.setPlainText(new_text)
        self.addWordsEdit.moveCursor(QTextCursor.MoveOperation.End)
        logger.debug(f"formatText: Formatted {len(words)} valid words")

    @staticmethod
    def all_strings_via_api(model, role=Qt.ItemDataRole.EditRole):
        strings = set()
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            value = model.data(idx, role)
            if value is not None:
                strings.add(str(value))
        return strings

    def accept(self):
        self.formatText()
        text = self.addWordsEdit.toPlainText()
        words = [word.strip().upper() for word in text.split("\n") if word.strip()]
        valid_words = [word for word in words if len(word) == self.word_length and word.isalpha()]
        if not valid_words:
            QMessageBox.warning(self, "Invalid Input", f"All words must be exactly {self.word_length} alphabetic characters.")
            return
        logger.debug(f"BatchAddDialog.accept: Returning {len(valid_words)} valid words")
        self.valid_words = valid_words  # Store for parent to access
        super().accept()



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
        logger.debug("ProgressDialog initialized, timer started")

        # self.timer = QTimer(self)
        # self.timer.setSingleShot(True)  # Ensure it only runs once


    def initUI(self):
        self.setupUi(self)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoTitleBarBackgroundHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        logger.debug(f"ProgressDialog window flags: {self.windowFlags()}")
        try:
            self.spinner.start()
            logger.debug("ProgressDialog spinner started")
        except AttributeError as e:
            logger.error(f"ProgressDialog spinner not properly initialized: {e}")
        self.cancelButton.clicked.connect(self.onCancelRequested)

    def updateLabel(self):
        # Update the label text with the current period
        base_text, *_ = self.label.text().split('<tt>')
        self.label.setText(base_text + next(self.last_periods))

    def onCancelRequested(self):
        self.spinner.setDisabled(True)
        self.label.setText("Canceling routes generation")
        logger.debug("Cancellation requested in ProgressDialog")
        if self.cancel_callback:
            try:
                self.cancel_callback()
                logger.debug("Called cancel_callback in ProgressDialog")
            except Exception as e:
                logger.error(f"Error executing cancel_callback: {e}")

    def keyPressEvent(self, event):
        logger.debug(f"ProgressDialog keyPressEvent: key={event.key()}, focusWidget={self.focusWidget()}")
        if event.key() == Qt.Key.Key_Escape:
            logger.debug("Esc key press in ProgressDialog, triggering onCancelRequested")
            self.onCancelRequested()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent):
        logger.debug("ProgressDialog closeEvent triggered")
        self.timer.stop()
        logger.debug("ProgressDialog timer stopped")
        try:
            self.spinner.stop()
            logger.debug("ProgressDialog spinner stopped")
        except AttributeError as e:
            logger.error(f"ProgressDialog spinner not properly initialized: {e}")
        super().closeEvent(event)

    def showDelayed(self, delay=500):
        """Show the dialog after a specified delay if it's not already visible."""
        if not self.isVisible():  # Check if the dialog is not already shown
            self.timer.timeout.connect(self.show)
            self.timer.start(delay)