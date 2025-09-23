from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QSortFilterProxyModel
from PyQt6.QtWidgets import QLineEdit, QMessageBox, QCompleter
from PyQt6.QtGui import QValidator
from ..delegates import UpperCaseValidator
from ..models import FilterProxy
import logging

logger = logging.getLogger(__name__)

class ConfirmLineEdit(QLineEdit):
    editorAction = pyqtSignal(str, str)  # (action: "yes"/"discard"/"continue", text)

    def __init__(self, profile=None, parent=None):
        super().__init__(parent)
        self.profile = profile
        self._dialog_active = False
        self._view = None
        self._item = None
        self.installEventFilter(self)
        logger.debug("ConfirmLineEdit.__init__: Initialized")

    def setProfile(self, profile):
        """Set the profile and update validator if needed."""
        self.profile = profile
        if profile and hasattr(self, 'validator') and self.validator():
            self.setValidator(UpperCaseValidator(profile.word_length, self))
        logger.debug("ConfirmLineEdit.setProfile: Profile set")

    def setContext(self, view, item):
        self._view = view
        self._item = item
        logger.debug(f"ConfirmLineEdit.setContext: Set view={type(view).__name__}, item_text={item.text() if item else 'None'}")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            text = self.text().strip().upper()
            choice = self._confirm_with_three_options()
            if choice == QMessageBox.StandardButton.Yes:
                if text:
                    self.editorAction.emit("yes", text)
                    logger.debug(f"ConfirmLineEdit.keyPressEvent: Emitted yes for '{text}'")
                else:
                    self.editorAction.emit("discard", "")
                    logger.debug("ConfirmLineEdit.keyPressEvent: Emitted discard for empty text")
            elif choice == QMessageBox.StandardButton.Discard:
                self.editorAction.emit("discard", "")
                logger.debug("ConfirmLineEdit.keyPressEvent: Emitted discard")
            else:  # Continue
                self.editorAction.emit("continue", text)
                QTimer.singleShot(0, lambda: [self.setFocus(Qt.FocusReason.PopupFocusReason), self.selectAll()])
                logger.debug("ConfirmLineEdit.keyPressEvent: Continue editing, kept editor open")
            return
        elif event.key() == Qt.Key.Key_Escape:
            self.editorAction.emit("discard", "")
            logger.debug("ConfirmLineEdit.keyPressEvent: Emitted discard on Escape")
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.FocusOut, QEvent.Type.Close, QEvent.Type.Hide) and self._dialog_active:
            logger.debug(f"ConfirmLineEdit.eventFilter: Blocked event {event.type()} during dialog")
            return True
        return super().eventFilter(obj, event)

    def focusOutEvent(self, event):
        if self._dialog_active:
            logger.debug("ConfirmLineEdit.focusOutEvent: Ignored focus out during dialog")
            return
        text = self.text().strip().upper()
        if text:
            choice = self._confirm_with_three_options()
            if choice == QMessageBox.StandardButton.Yes:
                if text:
                    self.editorAction.emit("yes", text)
                    logger.debug(f"ConfirmLineEdit.focusOutEvent: Emitted yes for '{text}'")
                else:
                    self.editorAction.emit("discard", "")
                    logger.debug("ConfirmLineEdit.focusOutEvent: Emitted discard for empty text")
            elif choice == QMessageBox.StandardButton.Discard:
                self.editorAction.emit("discard", "")
                logger.debug("ConfirmLineEdit.focusOutEvent: Emitted discard")
            else:  # Continue
                self.editorAction.emit("continue", text)
                QTimer.singleShot(0, lambda: [self.setFocus(Qt.FocusReason.PopupFocusReason), self.selectAll()])
                logger.debug("ConfirmLineEdit.focusOutEvent: Continue editing, kept editor open")
        else:
            self.editorAction.emit("discard", "")
            logger.debug("ConfirmLineEdit.focusOutEvent: Emitted discard for empty text")

    def _confirm_with_three_options(self) -> QMessageBox.StandardButton:
        word = self.text().strip().upper()
        if not word or not self.profile:
            return QMessageBox.StandardButton.Yes
        legal_picks = {self.profile.model.data(self.profile.model.index(i, 0), Qt.ItemDataRole.DisplayRole) for i in range(self.profile.model.rowCount())}
        if word in legal_picks:
            return QMessageBox.StandardButton.Yes
        self._dialog_active = True
        try:
            reply = QMessageBox.question(
                self.window(),
                "Add to Picks?",
                f"'{word}' is not in the legal picks. Add it to picks.txt?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Discard
            )
        finally:
            self._dialog_active = False
        logger.debug(f"ConfirmLineEdit._confirm_with_three_options: Reply={reply}")
        return reply

'''
WordEntryLineEdit:
    Q: could a model/proxy do validation?

    [.] confirmation predicate.
        confirmation action? (message, how to add to picks)
            or maybe combine/confirmation hook?
            # put this outside - connect return pressed?


    [how to add elments? (maybe taken care of by model)]

    [ ] custom proxy model what to exlcude: (initial picks + DT! / candidates) do both thru proxy model

    [ ] ***validation: canddiates: not in candidates (no dups)
                initial_picks: not in initial_pikc(no dups)

            manual set delegate:

    similarities:
        set A delagate/validation altho it's differetn
        completer.. altho its' different
        dialog/no dialog

    Delegate?? do we even set one? creates editor.. dont' need that.
        countermands blank entries: i 




PickEntryLineEdit

maybe just give them different filter proxys?
Q: Do the validators need to be re-initialized?

'''

class WordEntryLineEdit_orig(ConfirmLineEdit):
    def __init__(self, profile=None, parent=None):
        super().__init__(profile, parent)
        self._completer = None
        self._proxy_model = None
        self.setPlaceholderText('Enter a word...')
        if profile:
            self.setValidator(UpperCaseValidator(profile.word_length, self))
            self._setup_autocomplete()
        logger.debug("WordEntryLineEdit.__init__: Initialized")

    def setProfile(self, profile):
        """Set the profile and update validator and autocomplete."""
        super().setProfile(profile)
        if profile:
            self.setValidator(UpperCaseValidator(profile.word_length, self))
        self._setup_autocomplete()
        logger.debug(f"WordEntryLineEdit.setProfile: Profile set, model_rows={self.profile.model.rowCount() if self.profile and self.profile.model else 0}")

    def _setup_autocomplete(self):
        """Set up autocompleter for picks from profile.model."""
        if not self.profile or not self.profile.model:
            logger.debug("WordEntryLineEdit._setup_autocomplete: Skipped, profile or model not set")
            self.setCompleter(None)
            self._completer = None
            self._proxy_model = None
            return
        exclude = self.profile.initial_picks if hasattr(self.profile, 'initial_picks') and self.profile.initial_picks else set()
        self._proxy_model = FilterProxy(exclude, self)
        self._proxy_model.setSourceModel(self.profile.model)
        self._completer = QCompleter(self._proxy_model, self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCompletionColumn(0)
        self._completer.setCompletionRole(Qt.ItemDataRole.DisplayRole)
        self._completer.setMaxVisibleItems(10)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)  # Explicit mode
        # self._completer.popup().setMinimumWidth(200)  # Ensure visible size
        # self._completer.popup().setStyleSheet("QListView { font-size: 14px; background-color: #ffffff; border: 1px solid #000000; }")
        self.setCompleter(self._completer)
        logger.debug(f"WordEntryLineEdit._setup_autocomplete: Set QCompleter with FilterProxy, proxy_rows={self._proxy_model.rowCount() if self._proxy_model else 0}, exclude={exclude}")
        # Force completer query for debugging
        if self._completer:
            self._completer.setCompletionPrefix("")
            self._completer.complete()
            logger.debug(f"WordEntryLineEdit._setup_autocomplete: Forced complete, suggestions={self._completer.completionCount()}")

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        # Ensure editor is cleared and focused after action
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self.clear()
            QTimer.singleShot(0, lambda: [self.setFocus(Qt.FocusReason.PopupFocusReason), self.selectAll()])
            logger.debug(f"WordEntryLineEdit.keyPressEvent: Cleared and refocused, text={self.text()}, suggestions={self._completer.completionCount() if self._completer else 0}, popup_visible={self._completer.popup().isVisible() if self._completer else False}")



class CompleterLineEdit(ConfirmLineEdit):
    def __init__(self, proxy_model=None, validator=None, parent=None):
        super().__init__(profile, parent)
        self._completer = None
        self._proxy_model = proxy_model
        self.setPlaceholderText('Enter a word...')
        if validator:
            self.setValidator(validator)
        if model:
            self._setup_autocomplete()
        logger.debug("CompleterLineEdit.__init__: Initialized")

    def _setup_autocomplete(self):
        """Set up autocompleter for picks from profile.model."""
        if not self.model:
            logger.debug("WordEntryLineEdit._setup_autocomplete: Skipped, profile or model not set")
            self.setCompleter(None)
            self._completer = None
            self._proxy_model = None
            return
        self._completer = QCompleter(self._proxy_model, self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCompletionColumn(0)
        self._completer.setCompletionRole(Qt.ItemDataRole.DisplayRole)
        self._completer.setMaxVisibleItems(8)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)  # Explicit mode
        self.setCompleter(self._completer)
        logger.debug(f"CompleterLineEdit._setup_autocomplete: Set QCompleter with FilterProxy, proxy_rows={self._proxy_model.rowCount() if self._proxy_model else 0}")
        # Force completer query for debugging XXX maybe remove
        if self._completer:
            self._completer.setCompletionPrefix("")
            self._completer.complete()
            logger.debug(f"WordEntryLineEdit._setup_autocomplete: Forced complete, suggestions={self._completer.completionCount()}")

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        # Ensure editor is cleared and focused after action
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self.clear()
            QTimer.singleShot(0, lambda: [self.setFocus(Qt.FocusReason.PopupFocusReason), self.selectAll()])
            logger.debug(f"WordEntryLineEdit.keyPressEvent: Cleared and refocused, text={self.text()}, suggestions={self._completer.completionCount() if self._completer else 0}, popup_visible={self._completer.popup().isVisible() if self._completer else False}")



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
        # Force completer query for debugging
        if self._completer:
            self._completer.setCompletionPrefix("")
            self._completer.complete()
            logger.debug(f"WordEntryLineEdit._setup_autocomplete: Forced complete, suggestions={self._completer.completionCount()}")

    # def keyPressEvent(self, event):
    #     super().keyPressEvent(event)
    #     # Ensure editor is cleared and focused after action
    #     if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
    #         self.clear()
    #         QTimer.singleShot(0, lambda: [self.setFocus(Qt.FocusReason.PopupFocusReason), self.selectAll()])
    #         logger.debug(f"WordEntryLineEdit.keyPressEvent: Cleared and refocused, text={self.text()}, suggestions={self._completer.completionCount() if self._completer else 0}, popup_visible={self._completer.popup().isVisible() if self._completer else False}")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            super().keyPressEvent(event)  # lets QLineEdit emit returnPressed
            event.accept()                 # prevent further propagation (e.g., dialog)
            return
        super().keyPressEvent(event)