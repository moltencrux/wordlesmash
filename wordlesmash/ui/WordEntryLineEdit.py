from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QSortFilterProxyModel
from PyQt6.QtWidgets import QLineEdit, QMessageBox, QCompleter
from PyQt6.QtGui import QValidator
from ..delegates import UpperCaseValidator
from ..models import FilterProxy
import logging

logger = logging.getLogger(__name__)


class WordEntryLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._completer = None
        self._model = None
        self.setPlaceholderText('Enter a word..')
        logger.debug("WordEntryLineEdit.__init__: Initialized")

    def setCompleterModel(self, model):
        self._model = model
        self._setup_autocomplete()

    def _setup_autocomplete(self):
        """Set up autocompleter for picks from profile.model."""
        if not self._model:
            logger.debug("WordEntryLineEdit._setup_autocomplete: Skipped, profile or model not set")
            self.setCompleter(None)
            self._completer = None
            self._model = None
            return
        self._completer = QCompleter(self._model, self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive) # XXX necessary?
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCompletionColumn(0)
        self._completer.setCompletionRole(Qt.ItemDataRole.DisplayRole)
        self._completer.setMaxVisibleItems(10)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)  # Explicit mode
        self.setCompleter(self._completer)
        logger.debug(f"WordEntryLineEdit._setup_autocomplete: Set QCompleter with FilterProxy, proxy_rows={self._model.rowCount() if self._model else 0}")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            super().keyPressEvent(event)  # lets QLineEdit emit returnPressed
            event.accept()                # prevent further propagation (e.g., dialog)
            return
        super().keyPressEvent(event)