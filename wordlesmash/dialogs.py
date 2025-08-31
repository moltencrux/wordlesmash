from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtWidgets import QDialog
from PyQt6.QtGui import QCloseEvent
from .ui_loader import load_ui_class, UI_CLASSES
import logging
from itertools import cycle


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
