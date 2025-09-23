from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRect, QModelIndex, QEvent, QVariant, QEventLoop, QTimer, QStringListModel
from PyQt6.QtWidgets import QLineEdit, QItemDelegate, QStyledItemDelegate, QAbstractItemDelegate, QListWidget, QMessageBox, QListView, QListWidgetItem 
from PyQt6.QtGui import QValidator, QPainter, QFont, QColor
import logging

logger = logging.getLogger(__name__)

def wait_nonblocking(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class UpperCaseValidator(QValidator):
    def __init__(self, word_length, parent=None):
        super().__init__(parent)
        self.word_length = word_length
        self.cache = set()
        logger.debug(f"UpperCaseValidator initialized with word_length={word_length}")

    def validate(self, string, pos):
        string = string.strip().upper()
        if string in self.cache:
            logger.debug(f"UpperCaseValidator: Returning cached Acceptable for '{string}'")
            return QValidator.State.Acceptable, string, pos
        if len(string) == self.word_length and string.isalpha():
            state = QValidator.State.Acceptable
            self.cache.add(string)
            logger.debug(f"UpperCaseValidator: Cached Acceptable for '{string}'")
        elif string == '' or string.isalpha():
            state = QValidator.State.Intermediate
        else:
            state = QValidator.State.Invalid
        return state, string, pos

class PickValidator(UpperCaseValidator):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(word_length, parent)
        self.profile = profile

    def validate(self, string, pos):
        string = string.strip().upper()
        if string in self.cache:
            logger.debug(f"PickValidator: Returning cached Acceptable for '{string}'")
            return QValidator.State.Acceptable, string, pos
        elif self.profile.model._items.get(string) is not None:
            return QValidator.State.Intermediate, string, pos
        return super().validate(string, pos)

class CandidateValidator(UpperCaseValidator):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(word_length, parent)
        self.profile = profile

    def validate(self, string, pos):
        string = string.strip().upper()
        if string in self.cache:
            logger.debug(f"CandidateValidator: Returning cached Acceptable for '{string}'")
            return QValidator.State.Acceptable, string, pos
        elif string and self.profile.model._items.get(string) == 'candidate':
            logger.debug(f"CandidateValidator: '{string}' is a candidate")
            return QValidator.State.Intermediate, string, pos
        return super().validate(string, pos)

class InitialPickValidator(UpperCaseValidator):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(word_length, parent)
        self.profile = profile

    def validate(self, string, pos):
        string = string.strip().upper()
        if string in self.cache:
            logger.debug(f"InitialPickValidator: Returning cached Acceptable for '{string}'")
            return QValidator.State.Acceptable, string, pos
        elif string and (string in self.profile.initial_picks or string in self.profile.dt):
            logger.debug(f"InitialPickValidator: '{string}' is an initial pick")
            return QValidator.State.Intermediate, string, pos
        return super().validate(string, pos)

class UpperCaseDelegate(QItemDelegate):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(parent)
        self.current_index = QModelIndex()
        self.word_length = word_length
        self.profile = profile
        self.escape_pressed = False
        self._editor_index = {}
        self._editor_original = {}
        logger.debug(f"UpperCaseDelegate initialized with word_length={word_length}")
        self.closeEditor.connect(self.on_closeEditor)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        editor.installEventFilter(self)
        editor.setPlaceholderText('Enter a word...')
        self.applyValidator(editor)
        self._editor_index[editor] = QModelIndex(index)
        orig = index.model().data(index, Qt.ItemDataRole.EditRole) or ""
        self._editor_original[editor] = orig
        logger.debug(f"UpperCaseDelegate.createEditor: Created editor for index {index.row()}, orig='{orig}'")
        return editor

    def applyValidator(self, editor):
        editor.setValidator(UpperCaseValidator(self.word_length, editor))

    def eventFilter(self, editor, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.escape_pressed = True
            self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.RevertModelCache)
            logger.debug(f"UpperCaseDelegate.eventFilter: Escape pressed for editor at index {self._editor_index.get(editor, QModelIndex()).row()}")
            return True
        elif event.type() in (QEvent.Type.FocusOut, QEvent.Type.Close, QEvent.Type.Hide):
            logger.debug(f"UpperCaseDelegate.eventFilter: Ignored event {event.type()} for index {self._editor_index.get(editor, QModelIndex()).row()}")
            return True
        return super().eventFilter(editor, event)

    def on_closeEditor(self, editor, hint):
        logger.debug("UpperCaseDelegate.on_closeEditor: called")
        index = self._editor_index.get(editor)
        if not index or not index.isValid():
            logger.error(f"UpperCaseDelegate.on_closeEditor: Invalid index for editor")
            self._editor_index.pop(editor, None)
            self._editor_original.pop(editor, None)
            return
        orig = self._editor_original.get(editor, "")
        final = ""
        state = QValidator.State.Acceptable
        try:
            final = editor.text().strip().upper()
            state, _, _ = editor.validator().validate(final, 0)
        except RuntimeError:
            logger.debug("UpperCaseDelegate.on_closeEditor: Editor deleted, using last known text")
        valid = state == QValidator.State.Acceptable
        esc_on_blank = (orig == "" and hint == QAbstractItemDelegate.EndEditHint.RevertModelCache)
        logger.debug(f"UpperCaseDelegate.on_closeEditor: index={index.row()}, orig='{orig}', final='{final}', valid={valid}, esc_on_blank={esc_on_blank}, hint={hint}")
        if esc_on_blank or not valid:
            model = index.model()
            if model and 0 <= index.row() < model.rowCount():
                QTimer.singleShot(0, lambda: model.removeRow(index.row(), index.parent()))
                logger.debug(f"UpperCaseDelegate.on_closeEditor: Scheduled row {index.row()} removal")
            else:
                logger.error(f"UpperCaseDelegate.on_closeEditor: Cannot remove row {index.row()}, model_rows={model.rowCount() if model else 'None'}")
        self._editor_index.pop(editor, None)
        self._editor_original.pop(editor, None)

class InitialPicksDelegate(UpperCaseDelegate):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(word_length, profile, parent)
        self._view = parent  # QListWidget
        logger.debug("InitialPicksDelegate.__init__: Initialized for rendering and editor action handling")

    def createEditor(self, parent, option, index):
        logger.debug("InitialPicksDelegate.createEditor: Not used, handled by InitialPicksLineEdit")
        return None  # No editor needed, handled by InitialPicksLineEdit

    def handleEditorAction(self, action, text):
        """Handle InitialPicksLineEdit editorAction signal."""
        logger.debug(f"InitialPicksDelegate.handleEditorAction: action={action}, text='{text}'")
        if not self._view:
            logger.error("InitialPicksDelegate.handleEditorAction: No view set")
            return
        self._view.blockSignals(True)
        try:
            if action == "yes":
                if text:
                    self.profile.model.add_pick(text)
                    item = QListWidgetItem(text)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable)
                    self._view.addItem(item)
                    self._view.scrollToBottom()
                    logger.debug(f"InitialPicksDelegate.handleEditorAction: Added '{text}' to initialPicksList")
            elif action == "discard":
                logger.debug("InitialPicksDelegate.handleEditorAction: Discarded input")
            else:  # continue
                logger.debug(f"InitialPicksDelegate.handleEditorAction: Kept editor open with text '{text}'")
        finally:
            self._view.blockSignals(False)

class PicksDelegate(UpperCaseDelegate):
    def applyValidator(self, editor):
        editor.setValidator(PickValidator(self.word_length, self.profile, editor))
        logger.debug("PicksDelegate.applyValidator: Set PickValidator")

class CandidatesDelegate(UpperCaseDelegate):
    def applyValidator(self, editor):
        editor.setValidator(CandidateValidator(self.word_length, self.profile, editor))
        logger.debug("CandidatesDelegate.applyValidator: Set CandidateValidator")

class MultiBadgeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, badge_size=40, radius=6, font_px=20, spacing=6, left_padding=4):
        super().__init__(parent)
        self.badge_size = badge_size
        self.radius = radius
        self.font_px = font_px
        self.spacing = spacing
        self.left_padding = left_padding

    def paint(self, painter, option, index):
        data = index.data()
        if not data:
            super().paint(painter, option, index)
            return
        pairs = []
        for part in data.split(','):
            part = part.strip()
            if not part:
                continue
            if ':' in part:
                letter, color = part.split(':', 1)
            elif '|' in part:
                letter, color = part.split('|', 1)
            else:
                letter, color = part, "#777"
            pairs.append((letter.strip(), color.strip()))
        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont()
        font.setPixelSize(self.font_px)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        x = rect.x() + self.left_padding
        y = rect.y() + (rect.height() - self.badge_size) // 2
        for letter, color in pairs:
            badge_rect = QRect(x, y, self.badge_size, self.badge_size)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(badge_rect, self.radius, self.radius)
            painter.setPen(QColor("#ffffff"))
            text_w = fm.horizontalAdvance(letter)
            text_h = fm.height()
            tx = x + (self.badge_size - text_w) // 2
            ty = y + (self.badge_size - text_h) // 2 + fm.ascent()
            painter.drawText(tx, ty, letter)
            x += self.badge_size + self.spacing
            if x > rect.right():
                break
        painter.restore()

    def sizeHint(self, option, index):
        data = index.data() or ""
        count = sum(1 for p in data.split(',') if p.strip())
        if count == 0:
            return QSize(0, 0)
        total_w = self.left_padding + count * self.badge_size + (count - 1) * self.spacing + 4
        total_h = self.badge_size + 4
        return QSize(total_w, total_h)
