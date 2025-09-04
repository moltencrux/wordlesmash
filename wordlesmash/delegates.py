from PyQt6.QtCore import Qt, pyqtSlot, QSize, QRect, QModelIndex, QEvent, QVariant
from PyQt6.QtWidgets import QLineEdit, QItemDelegate, QStyledItemDelegate, QAbstractItemDelegate
from PyQt6.QtGui import QValidator, QPainter, QFont, QColor
import logging

logger = logging.getLogger(__name__)

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

class PickValidator(UpperCaseValidator):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(word_length, parent)
        self.profile = profile

    def validate(self, string, pos):
        if string.upper() in self.profile.picks:
            return QValidator.State.Intermediate, string.upper(), pos
        elif string.upper() in self.profile.candidates:
            return QValidator.State.Acceptable, string.upper(), pos
        else:
            return super().validate(string, pos)

class CandidateValidator(UpperCaseValidator):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(word_length, parent)
        self.profile = profile

    def validate(self, string, pos):
        if string.upper() in self.profile.candidates:
            return QValidator.State.Intermediate, string.upper(), pos
        else:
            return super().validate(string, pos)


class UpperCaseDelegate(QItemDelegate):
    def __init__(self, word_length, profile, parent=None):
        super().__init__(parent)
        self.current_index = QModelIndex()
        self.word_length = word_length
        self.profile = profile
        self.escape_pressed = False
        self._editor_index = {}  # Maps editor QWidget -> QModelIndex
        self._editor_original = {}  # Saves original text
        self._editor_processed = {}  # Tracks if editor was processed
        logger.debug(f"UpperCaseDelegate initialized with word_length={word_length}")

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        editor.installEventFilter(self)
        editor.setPlaceholderText('Enter a word...')
        self.applyValidator(editor)
        self._editor_index[editor] = QModelIndex(index)
        orig = index.model().data(index, Qt.ItemDataRole.EditRole) or ""
        self._editor_original[editor] = orig
        self._editor_processed[editor] = False
        logger.debug(f"UpperCaseDelegate.createEditor: Created editor for index {index.row()}, orig='{orig}'")
        return editor

    def applyValidator(self, editor):
        editor.setValidator(UpperCaseValidator(self.word_length, editor))

    def setEditorData(self, editor, index):
        text = index.model().data(index, Qt.ItemDataRole.EditRole) or ""
        editor.setText(str(text).upper())
        logger.debug(f"UpperCaseDelegate.setEditorData: Set text '{text}' for index {index.row()}")

    def setModelData(self, editor, model, index):
        text = editor.text().strip().upper()
        state = editor.validator().validate(text, 0)[0]
        logger.debug(f"UpperCaseDelegate.setModelData: Processing text '{text}', validator state={state}, index={index.row()}")
        if state == QValidator.State.Acceptable:
            model.setData(index, text, Qt.ItemDataRole.EditRole)
            logger.debug(f"UpperCaseDelegate.setModelData: Set valid text '{text}' for index {index.row()}")
        else:
            logger.debug(f"UpperCaseDelegate.setModelData: Skipped invalid/empty text '{text}' for index {index.row()}")

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def eventFilter(self, editor, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.escape_pressed = True
            self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.RevertModelCache)
            logger.debug(f"UpperCaseDelegate.eventFilter: Escape pressed for editor at index {self._editor_index.get(editor, QModelIndex()).row()}")
            return True
        return super().eventFilter(editor, event)

    # def eventFilter(self, editor, event):
    #     if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
    #         self.escape_pressed = True
    #         self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.RevertModelCache)
    #         logger.debug(f"UpperCaseDelegate.eventFilter: Escape pressed for editor at index {self.current_index.row()}")
    #         return True
    #     elif event.type() == QEvent.Type.FocusOut:
    #         logger.debug(f"UpperCaseDelegate.eventFilter: Ignored focus out event for editor at index {self.current_index.row()}")
    #         return True  # Prevent editor from closing
    #     return super().eventFilter(editor, event)


    # def on_closeEditor_old(self, editor, hint):
    #     # find index and state for this editor
    #     idx = self._editor_index.get(editor)
    #     committed = self._editor_committed.get(editor, False)
    #     orig = self._editor_original.get(editor, "")

    #     final = editor.text().strip()
    #     # validate final text explicitly
    #     state, _, _ = self._validator.validate(final, 0)
    #     valid = (state == QValidator.State.Acceptable)

    #     # If edit was not committed (Esc or cancel) and item started blank:
    #     # remove it when final is blank OR invalid.
    #     if idx is not None and not committed:
    #         if (final == "") or (not valid) or (orig == '' and not editor.isModified()):
    #             # (orig == '' and not .isModified) indicates a blank entry to start and esc was pressed
    #             if idx.isValid():
    #                 idx.model().removeRow(idx.row(), idx.parent())

    #     # cleanup mappings (WeakKeyDictionary would clear on deletion, but pop now)
    #     self._editor_index.pop(editor, None)
    #     self._editor_committed.pop(editor, None)
    #     self._editor_original.pop(editor, None)

    def on_closeEditor(self, editor, hint):
        logger.debug("UpperCaseDelegate.on_closeEditor: called")
        if self._editor_processed.get(editor, False):
            logger.debug("UpperCaseDelegate.on_closeEditor: Already processed, skipping")
            return
        index = self._editor_index.get(editor)
        if not index or not index.isValid():
            logger.error(f"UpperCaseDelegate.on_closeEditor: Invalid index for editor")
            self._editor_index.pop(editor, None)
            self._editor_original.pop(editor, None)
            self._editor_processed.pop(editor, None)
            return
        orig = self._editor_original.get(editor, "")
        final = editor.text().strip().upper()
        state, _, _ = editor.validator().validate(final, 0)
        valid = state == QValidator.State.Acceptable
        esc_on_blank = (orig == "" and hint == QAbstractItemDelegate.EndEditHint.RevertModelCache)
        logger.debug(f"UpperCaseDelegate.on_closeEditor: index={index.row()}, orig='{orig}', final='{final}', valid={valid}, esc_on_blank={esc_on_blank}, hint={hint}")
        if esc_on_blank or not valid:
            model = index.model()
            if model and 0 <= index.row() < model.rowCount():
                model.beginRemoveRows(index.parent(), index.row(), index.row())
                model.removeRow(index.row(), index.parent())
                model.endRemoveRows()
                logger.debug(f"UpperCaseDelegate.on_closeEditor: Removed row {index.row()} due to invalid/blank input")
            else:
                logger.error(f"UpperCaseDelegate.on_closeEditor: Cannot remove row {index.row()}, model_rows={model.rowCount() if model else 'None'}")
        self._editor_processed[editor] = True
        self._editor_index.pop(editor, None)
        self._editor_original.pop(editor, None)
        self._editor_processed.pop(editor, None)

    # def destroyEditor(self, editor, hint):
    #     # Remove no longer used per-editor references
    #     try:
    #         self._editor_index.pop(editor, None)
    #         self._editor_original.pop(editor, None)
    #     except Exception:
    #         pass
    #     super().destroyEditor(editor, hint)

class PicksDelegate(UpperCaseDelegate):

    def applyValidator(self, editor):
        editor.setValidator(PickValidator(self.word_length, self.profile, editor))
        logger.debug("PicksDelegate.applyValidator: Set PickValidator")

class CandidatesDelegate(UpperCaseDelegate):

    def applyValidator(self, editor):
        editor.setValidator(CandidateValidator(self.word_length, self.profile, editor))
        logger.debug("CandidatesDelegate.applyValidator: Set CandidateValidator")

    # def setModelData(self, editor, model, index):
    #     text = editor.text().strip().upper()
    #     state = editor.validator().validate(text, 0)[0]
    #     logger.debug(f"CandidatesDelegate.setModelData: Processing text '{text}', validator state={state}, index={index.row()}")
    #     if state == QValidator.State.Acceptable:
    #         # commit to model
    #         model.setData(index, text, Qt.ItemDataRole.EditRole)
    #         # update profile AFTER commit; guard reentrancy if needed
    #         self.profile.picks.add(text)
    #         logger.debug(f"CandidatesDelegate.setModelData: Set valid text '{text}' for index {index.row()} and added to profile.picks")
    #         # XXX picksList should be updated. should the Profile have a signal?
    #         # trigger sth... 
    #     else:
    #         model.setData(index, editor._old_value, Qt.ItemDataRole.EditRole)
    #         logger.debug(f"CandidatesDelegate.setModelData: Reverted to old_value '{editor._old_value}' for index {index.row()}")

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

        # Parse "A:#1976D2,B:#388E3C,..." into list of (letter, color)
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

        # font = QFont("Monospace")
        font = QFont()
        font.setPixelSize(self.font_px)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()

        # compute start x so badges are left-aligned with optional padding
        x = rect.x() + self.left_padding
        y = rect.y() + (rect.height() - self.badge_size) // 2


        for letter, color in pairs:
            badge_rect = QRect(x, y, self.badge_size, self.badge_size)

            # Draw rounded background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(badge_rect, self.radius, self.radius)

            # Draw letter centered
            painter.setPen(QColor("#ffffff"))
            text_w = fm.horizontalAdvance(letter)
            text_h = fm.height()  # Use full height (ascent + descent)

            # Horizontal centering
            tx = x + (self.badge_size - text_w) // 2
            # Vertical centering: baseline is at ascent above the bottom of the text
            ty = y + (self.badge_size - text_h) // 2 + fm.ascent()

            painter.drawText(tx, ty, letter)
            x += self.badge_size + self.spacing

            # Stop if overflow (optional)
            if x > rect.right():
                break

        painter.restore()

    def sizeHint(self, option, index):
        # Estimate width based on number of badges
        data = index.data() or ""
        count = sum(1 for p in data.split(',') if p.strip())
        if count == 0:
            return QSize(0, 0)
        total_w = self.left_padding + count * self.badge_size + (count - 1) * self.spacing + 4
        total_h = self.badge_size + 4
        return QSize(total_w, total_h)
