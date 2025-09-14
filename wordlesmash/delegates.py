from PyQt6.QtCore import Qt, pyqtSlot, QSize, QRect
from PyQt6.QtWidgets import QLineEdit, QItemDelegate, QStyledItemDelegate
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

class UpperCaseDelegate(QItemDelegate):
    def __init__(self, word_length, parent=None):
        super().__init__(parent)
        self.current_index = None
        self.word_length = word_length

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(UpperCaseValidator(self.word_length, editor))
        editor.setPlaceholderText('Enter a word...')
        self.current_index = index
        return editor


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
