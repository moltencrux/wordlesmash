from PyQt6.QtWidgets import (QApplication, QMainWindow, QTableWidget,
                             QTableWidgetItem, QAbstractItemView,
                             QFrame, QLabel, QVBoxLayout, QListWidget,
                             QListWidgetItem, QHBoxLayout, QWidget, QPushButton,
                             QGridLayout,)

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QBrush, QColor, QFont, QPalette, QKeyEvent
from string import ascii_uppercase
import sys
from collections.abc import Sequence, Iterable
from wordle_game import Color
from itertools import chain, islice



def get_next_color(current_color, allowed,
                   colors_index={v:k for k, v in enumerate(Color.__members__.values())},
                   colors=(*Color.__members__.values(),)):

    start = colors_index[current_color] + 1
    for color in chain(islice(colors, start, len(colors)), islice(colors, start)):
        if color in allowed:
            return color

    return Color.UNKNOWN

class CellFrame(QFrame):
    """Custom QFrame for cell with rounded corners, text, and dynamic border."""
    def __init__(self, text="", bg_color=Color.UNKNOWN, font_size=27, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._color = bg_color if isinstance(bg_color, Color) else Color.UNKNOWN
        # Layout and label
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
        self.label.setStyleSheet("border: none; background: transparent; outline: none;")
        self.label.setAutoFillBackground(False)
        self.label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.label)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Initial style
        self.updateStyle(False)
        self.updateTextColor()

    def _enum_to_hex(self, color):
        """Convert Color enum to hex string."""
        color_map = {
            Color.BLACK: "#000000",
            Color.YELLOW: "#c9b458",
            Color.GREEN: "#6aaa64",
            Color.UNKNOWN: "transparent"
        }
        return color_map.get(color, "transparent")

    def _hex_to_enum(self, hex_color):
        """Convert hex string to Color enum."""
        hex_map = {
            "#000000": Color.BLACK,
            "#c9b458": Color.YELLOW,
            "#6aaa64": Color.GREEN,
            "transparent": Color.UNKNOWN
        }
        return hex_map.get(hex_color.lower(), Color.UNKNOWN)

    @property
    def bg_color(self):
        """Get background color as hex string."""
        return self._enum_to_hex(self._color)

    @property
    def color(self):
        """Get color as Color enum."""
        return self._color

    def get_color(self):
        """Get color as hex string."""
        return self._enum_to_hex(self._color)

    def set_color(self, color):
        """Set color from Color enum or hex string."""
        if isinstance(color, Color):
            self._color = color
        else:
            self._color = self._hex_to_enum(color)
        self.updateStyle(self.styleSheet().find("white") != -1)
        self.updateTextColor()

    def updateStyle(self, is_selected):
        """Update border based on selection."""
        border_width = 3 if is_selected else 1
        border_color = "white" if is_selected else "#808080"
        bg_style = f"background-color: {self._enum_to_hex(self._color)};" if self._color != Color.UNKNOWN else ""
        self.setStyleSheet(
            f"""
            QFrame {{
                border: {border_width}px solid {border_color};
                border-radius: 5px;
                {bg_style}
            }}
            """
        )

    def updateTextColor(self):
        """Set text color based on background."""
        if self._color in [Color.BLACK, Color.GREEN, Color.YELLOW]:
            self.label.setStyleSheet("color: white; border: none; background: transparent; outline: none;")
        else:
            self.label.setStyleSheet("color: inherit; border: none; background: transparent; outline: none;")

    def setText(self, text):
        """Update label text."""
        self.label.setText(text)

    def setBackground(self, color):
        """Update background color and text color (legacy, use set_color)."""
        self.set_color(color)

    def setFont(self, font):
        """Update label font."""
        self.label.setFont(font)

    def text(self):
        """Get label text."""
        return self.label.text()

class WordTableWidget(QTableWidget):
    # Custom signal for when a new row is added (word and colors submitted)
    wordSubmitted = pyqtSignal(str, list)
    wordWithdrawn = pyqtSignal()

    def __init__(self, rows=1, cols=5, color_callback=None, parent=None):
        super().__init__(rows, cols, parent)
        self._submitEnabled = True
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setShowGrid(False)
        self.font_size_ratio = 0.4
        if not 0.1 <= self.font_size_ratio <= 1.0:
            self.font_size_ratio = 0.4
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setStyleSheet(
            """
            QTableWidget {
                background-color: transparent;
                border: none;
                margin: 0px;
            }
            QTableWidget::item {
                border: none;
                padding: 5px !important;
            }
            """
        )
        palette = self.palette()
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
        self.setPalette(palette)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setFixedHeight(0)
        self.color_callback = color_callback if color_callback else self.default_color_callback
        self.allowed_colors = [[Color.UNKNOWN] for _ in range(self.columnCount())]
        self.initializeCells()
        self.prev_focused_cell = (self.rowCount() - 1, 0)
        self.update_allowed_colors()
        self.currentCellChanged.connect(self.updateFocusStyle)
        self.cellPressed.connect(self.handleCellPressed)
        # Repeated presses are only emitted as double clicks by QTableWidget
        self.cellDoubleClicked.connect(self.handleCellPressed)
        self.setCurrentCell(self.rowCount() - 1, 0)

        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

    def default_color_callback(self, letters):
        """Default callback using Color enum."""
        allowed = []
        for letter in letters:
            if not letter:
                allowed.append([Color.UNKNOWN])
            elif letter in "AEIOU":
                allowed.append([Color.GREEN, Color.YELLOW])
            else:
                allowed.append([Color.BLACK, Color.GREEN])
        print(f"default_color_callback: letters={letters}, allowed={[ [c.name for c in colors] for colors in allowed]}")
        return allowed

    def getCurrentEntry(self):
        last_row = self.rowCount() - 1
        if last_row >= 0:
            letters = [self.cellWidget(last_row, c).text() for c in range(self.columnCount())]
            # letters = [c if c != '' else None for c in letters]
        else:
            return [''] * self.columnCount()
        return letters


    def set_color_callback(self, new_callback):
        """Set a new color callback and update allowed colors."""
        if not callable(new_callback):
            print(f"set_color_callback: Invalid callback, using default")
            self.color_callback = self.default_color_callback
        else:
            self.color_callback = new_callback
            last_row = self.rowCount() - 1
            letters = [self.cellWidget(last_row, c).text() for c in range(self.columnCount())]
            try:
                test_allowed = self.color_callback(letters)
                valid_colors = [Color.BLACK, Color.YELLOW, Color.GREEN, Color.UNKNOWN]
                if not isinstance(test_allowed, Sequence) or len(test_allowed) != self.columnCount():
                    print(f"set_color_callback: Expected sequence of {self.columnCount()} iterables, got {test_allowed}")
                    self.color_callback = self.default_color_callback
                else:
                    for i, colors in enumerate(test_allowed):
                        if not isinstance(colors, Iterable) or not colors:
                            print(f"set_color_callback: Invalid colors for col {i}: expected non-empty iterable, got {colors}")
                            self.color_callback = self.default_color_callback
                            break
                        if not all(isinstance(c, Color) and c in valid_colors for c in colors):
                            print(f"set_color_callback: Invalid color in col {i}: {colors}")
                            self.color_callback = self.default_color_callback
                            break
            except Exception as e:
                print(f"set_color_callback: Callback error {e}, using default")
                self.color_callback = self.default_color_callback
        self.update_allowed_colors()
        print(f"set_color_callback: Set new callback, allowed_colors={[ [c.name for c in colors] for colors in self.allowed_colors]}")

    def get_allowed_colors(self):
        """Get allowed colors via callback, keep as Color enums."""
        letters = self.getCurrentEntry()

        try:
            allowed = self.color_callback(letters)
            if not isinstance(allowed, Sequence) or len(allowed) != self.columnCount():
                print(f"get_allowed_colors: Expected sequence of {self.columnCount()} iterables, got {allowed}")
                return [[Color.UNKNOWN] for _ in range(self.columnCount())]
            enum_allowed = []
            valid_colors = [*Color.__members__.values()]
            for i, colors in enumerate(allowed):
                if not isinstance(colors, Iterable) or not colors:
                    print(f"get_allowed_colors: Invalid colors for col {i}: expected non-empty iterable, got {colors}")
                    enum_allowed.append([Color.UNKNOWN])
                    continue
                valid = [c for c in colors if isinstance(c, Color) and c in valid_colors]
                enum_allowed.append(list(valid) if valid else [Color.UNKNOWN])
            print(f"get_allowed_colors: letters={letters}, allowed={[ [c.name for c in colors] for colors in enum_allowed]}")
            return enum_allowed
        except Exception as e:
            print(f"get_allowed_colors: Callback error {e}")
            return [[Color.UNKNOWN] for _ in range(self.columnCount())]

    def update_allowed_colors(self):
        """Update cached allowed colors for the last row."""
        self.allowed_colors = self.get_allowed_colors()
        valid_colors = [Color.BLACK, Color.YELLOW, Color.GREEN, Color.UNKNOWN]
        for i, colors in enumerate(self.allowed_colors):
            if not isinstance(colors, list) or not colors:
                print(f"update_allowed_colors: Invalid colors for col {i}: {colors}")
                self.allowed_colors[i] = [Color.UNKNOWN]
                continue
            if not all(isinstance(c, Color) and c in valid_colors for c in colors):
                print(f"update_allowed_colors: Invalid colors in col {i}: {[c.name if isinstance(c, Color) else c for c in colors]}")
                self.allowed_colors[i] = [Color.UNKNOWN]
        print(f"Updated allowed_colors: {[ [c.name for c in colors] for colors in self.allowed_colors]}")


    def clear(self):
        """Override clear to reset to one blank row."""
        super().clear()
        self.setRowCount(1)
        self.setColumnCount(5)
        self.initializeCells()
        self.setCurrentCell(0, 0)
        self.prev_focused_cell = (0, 0)
        self.updateCellSizes()
        self.update_allowed_colors()
        print("Table cleared: Reset to 1 blank row")

    @pyqtSlot(QListWidgetItem)
    def onListItemSelected(self, item):
        if item is not None and self.rowCount() > 0:
            text = item.text()
            self.setLastRowText(text)
            print(f"Slot onListItemSelected: Set last row to '{text}'")
        else:
            print("Slot onListItemSelected: No rows or None item")

    @pyqtSlot()
    def onVirtualKeyPressed(self):
        """Slot to handle virtual keyboard button clicks."""
        button = self.sender()
        if button and isinstance(button, QPushButton):
            key_name = button.property('keyName') or 'Key_' + button.text().upper()
            key = getattr(Qt.Key, key_name, None)
            if key:
                event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, key_name)
                self.keyPressEvent(event)
                print(f"Virtual key pressed: '{key_name}'")
            else:
                print(f"Invalid virtual key: '{key_name}'")
        else:
            print("Virtual key pressed: No valid sender")

    def setLastRowText(self, string):
        if self.rowCount() == 0:
            print("setLastRowText: No rows available")
            return
        last_row = self.rowCount() - 1
        viewport_width = self.viewport().width()
        cell_size = viewport_width // self.columnCount()
        inner_size = cell_size - 2 - 10
        font_size = int(inner_size * self.font_size_ratio)

        for col in range(self.columnCount()):
            frame = self.cellWidget(last_row, col)
            if frame:
                if col < len(string) and string[col].isalpha():
                    frame.setText(string[col].upper())
                    allowed = self.allowed_colors[col]
                    color = allowed[0] if allowed and allowed[0] != Color.UNKNOWN else Color.BLACK
                    frame.set_color(color)
                else:
                    frame.setText("")
                    frame.set_color(Color.UNKNOWN)
                frame.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                frame.updateStyle(last_row == self.currentRow() and col == self.currentColumn())

        focus_col = min(len([c for c in string[:self.columnCount()] if c.isalpha()]), self.columnCount() - 1)
        self.setCurrentCell(last_row, focus_col)
        self.prev_focused_cell = (last_row, focus_col)
        self.update_allowed_colors()
        print(f"Set last row text: '{string}', focus: row={last_row}, col={focus_col}")
        self.viewport().update()

    def initializeCells(self):
        """Set up empty cells with QFrame and transparent background."""
        temp_size = 50
        font_size = int(temp_size * self.font_size_ratio)
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                if not self.cellWidget(row, col):
                    frame = CellFrame("", Color.UNKNOWN, font_size)
                    self.setCellWidget(row, col, frame)
                    self.setColumnWidth(col, temp_size)
                    self.setRowHeight(row, temp_size)
                    frame.setMinimumSize(temp_size - 12, temp_size - 12)
                    frame.setMaximumSize(temp_size - 12, temp_size - 12)

    def updateCellSizes(self):
        """Update cell sizes based on viewport."""
        viewport_width = self.viewport().width()
        cell_size = viewport_width // self.columnCount()
        inner_size = cell_size - 2 - 10
        font_size = int(inner_size * self.font_size_ratio)
        for row in range(self.rowCount()):
            self.setRowHeight(row, cell_size)
            for col in range(self.columnCount()):
                self.setColumnWidth(col, cell_size)
                frame = self.cellWidget(row, col)
                if frame:
                    frame.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                    frame.setMinimumSize(inner_size, inner_size)
                    frame.setMaximumSize(inner_size, inner_size)
        print(f"Updated: Cell size={cell_size}, Inner size={inner_size}, Viewport={viewport_width}")

    def resizeEvent(self, event):
        """Ensure cells are square and update font size."""
        super().resizeEvent(event)
        self.updateCellSizes()

    def updateFocusStyle(self, currentRow, currentCol, previousRow, previousCol):
        """Update border for selected cell, only in last row."""
        if currentRow == self.rowCount() - 1 and currentCol >= 0:
            if previousRow >= 0 and previousCol >= 0:
                prev_frame = self.cellWidget(previousRow, previousCol)
                if prev_frame:
                    prev_frame.updateStyle(False)
            curr_frame = self.cellWidget(currentRow, currentCol)
            if curr_frame:
                curr_frame.updateStyle(True)


    @pyqtSlot(int, int)
    def handleCellPressed(self, row, col):
        frame = self.cellWidget(row, col)
        if row != self.rowCount() - 1 or not frame.text():
            return
        allowed = self.allowed_colors[col]
        valid_colors = [Color.BLACK, Color.YELLOW, Color.GREEN, Color.UNKNOWN]
        if not allowed or not all(isinstance(c, Color) and c in valid_colors for c in allowed):
            allowed = [Color.BLACK]
        if allowed and allowed != [Color.UNKNOWN]:
            current_color = frame.color
            next_color = get_next_color(current_color, allowed)
            frame.set_color(next_color)
            frame.update()
            print(f"Cell pressed: row={row}, col={col}, text={frame.text()}, cycled {current_color.name} -> {next_color.name}")


    def keyPressEvent(self, event):
        """Handle letter keys, Enter, Backspace, and navigation, only in final row."""
        key = event.key()
        current_row = self.currentRow()
        current_col = self.currentColumn()
        if self.rowCount() == 0 or current_row < 0 or current_row >= self.rowCount():
            print(f"keyPressEvent: Invalid state - rows={self.rowCount()}, current_row={current_row}")
            return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and current_row == self.rowCount() - 1:
            if key == Qt.Key.Key_Left and current_col > 0:
                self.setCurrentCell(current_row, current_col - 1)
                self.prev_focused_cell = (current_row, current_col - 1)
                print(f"Navigated: row={current_row}, col={current_col - 1}, prev_focused={self.prev_focused_cell}")
            elif key == Qt.Key.Key_Right and current_col < self.columnCount() - 1:
                self.setCurrentCell(current_row, current_col + 1)
                self.prev_focused_cell = (current_row, current_col + 1)
                print(f"Navigated: row={current_row}, col={current_col + 1}, prev_focused={self.prev_focused_cell}")
            return

        if (
            Qt.Key.Key_A <= key <= Qt.Key.Key_Z
            and current_row >= 0
            and current_col >= 0
            and current_row == self.rowCount() - 1
        ):
            letter = chr(key).upper()
            frame = self.cellWidget(current_row, current_col)
            if frame:
                frame.setText(letter)
                self.update_allowed_colors()
                allowed = self.allowed_colors[current_col]
                color = allowed[0] if allowed and allowed[0] != Color.UNKNOWN else Color.BLACK
                frame.set_color(color)
                viewport_width = self.viewport().width()
                cell_size = viewport_width // self.columnCount()
                inner_size = cell_size - 2 - 10
                font_size = int(inner_size * self.font_size_ratio)
                frame.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                frame.updateStyle(current_row == self.currentRow() and current_col == self.currentColumn())
                if current_col < self.columnCount() - 1:
                    self.setCurrentCell(current_row, current_col + 1)
                    self.prev_focused_cell = (current_row, current_col + 1)
                    print(f"Text input: row={current_row}, col={current_col + 1}, letter={letter}, color={color.name}")
            return

        if (key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter) and self._submitEnabled:
            if current_row == self.rowCount() - 1:
                row_filled = all(
                    self.cellWidget(current_row, c) and self.cellWidget(current_row, c).text()
                    for c in range(self.columnCount())
                )
                if row_filled:
                    word = ''.join(self.cellWidget(current_row, c).text() for c in range(self.columnCount()))
                    enum_colors = [self.cellWidget(current_row, c).color for c in range(self.columnCount())]
                    self.wordSubmitted.emit(word, enum_colors)
                    print(f"Emitted wordSubmitted: word='{word}', colors={[c.name for c in enum_colors]}")
                    new_row = self.rowCount()
                    self.insertRow(new_row)
                    viewport_width = self.viewport().width()
                    cell_size = viewport_width // self.columnCount()
                    inner_size = cell_size - 2 - 10
                    font_size = int(inner_size * self.font_size_ratio)
                    for col in range(self.columnCount()):
                        frame = CellFrame("", Color.UNKNOWN, font_size)
                        self.setCellWidget(new_row, col, frame)
                        frame.setMinimumSize(inner_size, inner_size)
                        frame.setMaximumSize(inner_size, inner_size)
                    self.setRowHeight(new_row, cell_size)
                    self.setCurrentCell(new_row, 0)
                    self.prev_focused_cell = (new_row, 0)
                    self.update_allowed_colors()
                    print(f"Enter: row={new_row}, col=0, prev_focused={self.prev_focused_cell}")
            return

        if (
            key == Qt.Key.Key_Backspace
            and current_row >= 0
            and current_col >= 0
            and current_row == self.rowCount() - 1
        ):
            frame = self.cellWidget(current_row, current_col)
            row_empty = all(
                self.cellWidget(current_row, c) and not self.cellWidget(current_row, c).text()
                for c in range(self.columnCount())
            )
            if current_col == 0 and row_empty and self.rowCount() > 1 and self._submitEnabled:
                print(f"Deleting empty row {current_row}")
                self.removeRow(current_row)
                self.wordWithdrawn.emit()
                print(f"Emitted wordWithdrawn")
                new_row = self.rowCount() - 1
                new_col = self.columnCount() - 1
                self.setCurrentCell(new_row, new_col)
                self.prev_focused_cell = (new_row, new_col)
                self.update_allowed_colors()
                print(f"Backspace delete: row={new_row}, col={new_col}, prev_focused={self.prev_focused_cell}")
            else:
                if frame:
                    frame.setText("")
                    frame.set_color(Color.UNKNOWN)
                    viewport_width = self.viewport().width()
                    cell_size = viewport_width // self.columnCount()
                    inner_size = cell_size - 2 - 10
                    font_size = int(inner_size * self.font_size_ratio)
                    frame.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                    frame.updateStyle(current_row == self.currentRow() and current_col == self.currentColumn())
                    self.update_allowed_colors()
                if current_col > 0:
                    self.setCurrentCell(current_row, current_col - 1)
                    self.prev_focused_cell = (current_row, current_col - 1)
                    print(f"Backspace: row={current_row}, col={current_col - 1}, prev_focused={self.prev_focused_cell}")
            return

        super().keyPressEvent(event)

    def setSubmitEnabled(self, state=True):
        self._submitEnabled = bool(state)

    def setSubmitDisabled(self, state=True):
        self.setSubmitEnabled(not state)

    def getHistory(self):
        """Return words and colors from previous rows."""
        words = []
        clue_colors = []
        for row in range(self.rowCount() - 1):
            word = ''.join(self.cellWidget(row, c).text() for c in range(self.columnCount()))
            words.append(word)
            colors = tuple(self.cellWidget(row, c).color for c in range(self.columnCount()))
            clue_colors.append(colors)
        return words, clue_colors

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Word Table Test")
        self.setGeometry(100, 100, 600, 400)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)
        self.table = WordTableWidget(rows=1, cols=5, parent=self)
        top_layout.addWidget(self.table)
        self.list_widget = QListWidget(self)
        for word in ["hello", "world", "hi", "hi123", "toolongword"]:
            self.list_widget.addItem(QListWidgetItem(word))
        self.list_widget.setMaximumWidth(150)
        top_layout.addWidget(self.list_widget)
        keyboard_widget = QWidget(self)
        keyboard_layout = QGridLayout(keyboard_widget)
        keyboard_layout.setSpacing(5)
        letters = list(ascii_uppercase)
        button_size = 40
        positions = [(0, i) for i in range(10)] + [(1, i) for i in range(9)] + [(2, i) for i in range(7)]
        self.buttons = {}
        for letter, (row, col) in zip(letters, positions):
            button = QPushButton(letter, keyboard_widget)
            button.setFixedSize(button_size, button_size)
            button.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            keyboard_layout.addWidget(button, row, col)
            self.buttons[letter] = button
        enter_button = QPushButton("ENTER", keyboard_widget)
        enter_button.setFixedSize(60, button_size)
        enter_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        enter_button.setProperty('keyName', 'Key_Enter')
        keyboard_layout.addWidget(enter_button, 2, 7)
        back_button = QPushButton("BACK", keyboard_widget)
        back_button.setFixedSize(60, button_size)
        back_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        back_button.setProperty('keyName', 'Key_Backspace')
        keyboard_layout.addWidget(back_button, 2, 8)
        reset_button = QPushButton("RESET", keyboard_widget)
        reset_button.setFixedSize(60, button_size)
        reset_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        reset_button.setProperty('keyName', 'Key_Delete')
        keyboard_layout.addWidget(reset_button, 2, 9)
        main_layout.addWidget(keyboard_widget)
        self.list_widget.itemClicked.connect(self.table.onListItemSelected)
        self.table.wordSubmitted.connect(self.onWordSubmitted)
        self.table.wordWithdrawn.connect(self.onWordWithdrawn)
        for letter, button in self.buttons.items():
            button.clicked.connect(self.table.onVirtualKeyPressed)
        enter_button.clicked.connect(self.table.onVirtualKeyPressed)
        back_button.clicked.connect(self.table.onVirtualKeyPressed)
        reset_button.clicked.connect(self.table.clear)
        self.table.set_color_callback(self.table.default_color_callback)
        QApplication.instance().setDoubleClickInterval(100)

    def onWordSubmitted(self, word, colors):
        print(f"Received wordSubmitted: word='{word}', colors={[c.name for c in colors]}")
        ordinal = Color.ordinal(tuple(colors))
        print(f"Ordinal value: {ordinal}")

    def onWordWithdrawn(self):
        print(f"Received wordWithdrawn")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
