from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QFrame,
    QLabel,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QBrush, QColor, QFont, QPalette, QKeyEvent
from string import ascii_uppercase
import sys

class CellFrame(QFrame):
    """Custom QFrame for cell with rounded corners, text, and dynamic border."""
    def __init__(self, text="", bg_color="transparent", font_size=27, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.bg_color = bg_color
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

    def updateStyle(self, is_selected):
        """Update border based on selection."""
        border_width = 3 if is_selected else 1
        border_color = "white" if is_selected else "#808080"
        bg_style = f"background-color: {self.bg_color};" if self.bg_color != "transparent" else ""
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
        if self.bg_color in ["#000000", "#6aaa64", "#c9b458"]:
            self.label.setStyleSheet("color: white; border: none; background: transparent; outline: none;")
        else:  # transparent
            self.label.setStyleSheet("color: inherit; border: none; background: transparent; outline: none;")

    def setText(self, text):
        """Update label text."""
        self.label.setText(text)

    def setBackground(self, color):
        """Update background color and text color."""
        self.bg_color = color
        self.updateStyle(self.styleSheet().find("white") != -1)
        self.updateTextColor()

    def setFont(self, font):
        """Update label font."""
        self.label.setFont(font)

    def text(self):
        """Get label text."""
        return self.label.text()

class WordTableWidget(QTableWidget):
    # Custom signal for when a new row is added (word and colors submitted)
    wordSubmitted = pyqtSignal(str, list)
    wordWithdrawn = pyqtSignal()  # Renamed and simplified signal for row deletion

    def __init__(self, rows=1, cols=5, parent=None):
        super().__init__(rows, cols, parent)
        self._submitEnabled = True
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setShowGrid(False)  # No grid lines
        # Font size ratio attribute
        self.font_size_ratio = 0.4  # Default to 0.4
        if not 0.1 <= self.font_size_ratio <= 1.0:
            self.font_size_ratio = 0.4  # Reset to default if invalid
        # Enable smooth scrolling
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # Stylesheet with padding on item
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

        # Set palette to minimize highlight
        palette = self.palette()
        palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
        self.setPalette(palette)

        # Scrollbar policies
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Hide headers and fix row 0
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setFixedHeight(0)

        # Initialize cells with QFrame (placeholder sizes)
        self.initializeCells()

        # Track focus
        self.prev_focused_cell = (self.rowCount() - 1, 0)

        # Connect signals
        self.currentCellChanged.connect(self.updateFocusStyle)
        self.cellClicked.connect(self.handleCellClicked)
        self.cellDoubleClicked.connect(self.handleCellDoubleClicked)

        # Set initial focus to last row, col 0
        self.setCurrentCell(self.rowCount() - 1, 0)

    def clear(self):
        """Override clear to reset to one blank row."""
        super().clear()
        self.setRowCount(1)
        self.setColumnCount(5)
        self.initializeCells()
        self.setCurrentCell(0, 0)
        self.prev_focused_cell = (0, 0)
        self.updateCellSizes()
        print("Table cleared: Reset to 1 blank row")

    @pyqtSlot(QListWidgetItem)
    def onListItemSelected(self, item):
        """Slot to handle QListWidgetItem selection, sets last row text."""
        if item is not None:
            text = item.text()
            self.setLastRowText(text)
            print(f"Slot onListItemSelected: Set last row to '{text}'")
        else:
            print("Slot onListItemSelected: Received None item")

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
                print(f"Virtual key pressed: '{key}'")
            else:
                print(f"Invalid virtual key: '{key}'")
        else:
            print("Virtual key pressed: No valid sender")

    def setLastRowText(self, string):
        """Set last row cells to characters from string, position matching column."""
        last_row = self.rowCount() - 1
        # Update cell sizes to ensure font consistency
        viewport_width = self.viewport().width()
        cell_size = viewport_width // self.columnCount()
        inner_size = cell_size - 2 - 10  # 2px borders, 10px padding
        font_size = int(inner_size * self.font_size_ratio)

        # Process each column
        for col in range(self.columnCount()):
            frame = self.cellWidget(last_row, col)
            if frame:
                if col < len(string) and string[col].isalpha():
                    # Set letter (uppercase), black background
                    frame.setText(string[col].upper())
                    frame.setBackground("#000000")
                else:
                    # Clear cell, transparent background
                    frame.setText("")
                    frame.setBackground("transparent")
                # Update font
                frame.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                # Update style (focus only on current cell)
                frame.updateStyle(last_row == self.currentRow() and col == self.currentColumn())

        # Set focus: first empty column or last column if full
        focus_col = min(len([c for c in string[:self.columnCount()] if c.isalpha()]), self.columnCount() - 1)
        self.setCurrentCell(last_row, focus_col)
        self.prev_focused_cell = (last_row, focus_col)
        print(f"Set last row text: '{string}', focus: row={last_row}, col={focus_col}")
        self.viewport().update()

    def initializeCells(self):
        """Set up empty cells with QFrame and transparent background."""
        temp_size = 50  # Placeholder
        font_size = int(temp_size * self.font_size_ratio)
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                if not self.cellWidget(row, col):  # Only set if not already set
                    frame = CellFrame("", "transparent", font_size)
                    self.setCellWidget(row, col, frame)
                    self.setColumnWidth(col, temp_size)
                    self.setRowHeight(row, temp_size)
                    frame.setMinimumSize(temp_size - 12, temp_size - 12)
                    frame.setMaximumSize(temp_size - 12, temp_size - 12)

    def updateCellSizes(self):
        """Update cell sizes based on viewport."""
        viewport_width = self.viewport().width()
        cell_size = viewport_width // self.columnCount()
        inner_size = cell_size - 2 - 10  # 2px borders, 10px padding
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
        """Update border for selected cell, only in last row, preserve focus if invalid."""
        if currentRow == self.rowCount() - 1 and currentCol >= 0:
            if previousRow >= 0 and previousCol >= 0:
                prev_frame = self.cellWidget(previousRow, previousCol)
                if prev_frame:
                    prev_frame.updateStyle(False)
            curr_frame = self.cellWidget(currentRow, currentCol)
            if curr_frame:
                curr_frame.updateStyle(True)

    def handleCellClicked(self, row, col):
        """Handle single clicks for focus and color cycling, only in last row."""
        if row != self.rowCount() - 1:
            return  # Ignore upper rows, keep current focus
        frame = self.cellWidget(row, col)
        print(f"Single clicked: row={row}, col={col}, text={frame.text()}, prev_focused={self.prev_focused_cell}")
        # Cycle colors if already focused, in final row, and has text
        if (
            row == self.rowCount() - 1
            and frame.text()
            and self.prev_focused_cell == (row, col)
        ):
            current_color = frame.bg_color
            print(f"Current color: {current_color}")
            if current_color == "#000000":  # Black
                frame.setBackground("#6aaa64")  # Green
            elif current_color == "#6aaa64":  # Green
                frame.setBackground("#c9b458")  # Yellow
            elif current_color == "#c9b458":  # Yellow
                frame.setBackground("#000000")  # Black
            new_color = frame.bg_color
            print(f"Set color to: {new_color}")
            frame.updateStyle(row == self.currentRow() and col == self.currentColumn())
            self.update()
        # Update previous focus
        self.prev_focused_cell = (row, col)

    def handleCellDoubleClicked(self, row, col):
        """Handle double clicks for color cycling, only in last row."""
        if row != self.rowCount() - 1:
            return  # Ignore upper rows, keep current focus
        frame = self.cellWidget(row, col)
        print(f"Double clicked: row={row}, col={col}, text={frame.text()}, prev_focused={self.prev_focused_cell}")
        # Cycle colors in final row if has text, no focus check
        if row == self.rowCount() - 1 and frame.text():
            current_color = frame.bg_color
            print(f"Current color: {current_color}")
            if current_color == "#000000":  # Black
                frame.setBackground("#6aaa64")  # Green
            elif current_color == "#6aaa64":  # Green
                frame.setBackground("#c9b458")  # Yellow
            elif current_color == "#c9b458":  # Yellow
                frame.setBackground("#000000")  # Black
            new_color = frame.bg_color
            print(f"Set color to: {new_color}")
            frame.updateStyle(row == self.currentRow() and col == self.currentColumn())
            self.update()
        # Update previous focus
        self.prev_focused_cell = (row, col)

    def keyPressEvent(self, event):
        """Handle letter keys, Enter, Backspace, and navigation, only in final row."""
        key = event.key()
        current_row = self.currentRow()
        current_col = self.currentColumn()

        # Restrict navigation to last row
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # No-op: Prevent moving to upper rows
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

        # Only allow text input in final row
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
                frame.setBackground("#000000")  # Black
                # Update font size
                viewport_width = self.viewport().width()
                cell_size = viewport_width // self.columnCount()
                inner_size = cell_size - 2 - 10
                font_size = int(inner_size * self.font_size_ratio)
                frame.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                frame.updateStyle(current_row == self.currentRow() and current_col == self.currentColumn())
                self.viewport().update()
                if current_col < self.columnCount() - 1:
                    self.setCurrentCell(current_row, current_col + 1)
                    self.prev_focused_cell = (current_row, current_col + 1)
                    print(f"Text input: row={current_row}, col={current_col + 1}, prev_focused={self.prev_focused_cell}")
            return

        # Enter: Add new row if final row is filled, regardless of focused column
        if (key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter) and self._submitEnabled:
            if current_row == self.rowCount() - 1:
                row_filled = all(
                    self.cellWidget(current_row, c) and self.cellWidget(current_row, c).text()
                    for c in range(self.columnCount())
                )
                if row_filled:
                    # Get word and colors from current last row
                    word = ''.join(self.cellWidget(current_row, c).text() for c in range(self.columnCount()))
                    colors = [self.cellWidget(current_row, c).bg_color for c in range(self.columnCount())]
                    # Add new row
                    new_row = self.rowCount()
                    self.insertRow(new_row)
                    # Emit signal with word and colors
                    self.wordSubmitted.emit(word, colors)
                    print(f"Emitted wordSubmitted: word='{word}', colors={colors}")
                    # Set up new row
                    viewport_width = self.viewport().width()
                    cell_size = viewport_width // self.columnCount()
                    inner_size = cell_size - 2 - 10
                    font_size = int(inner_size * self.font_size_ratio)
                    for col in range(self.columnCount()):
                        frame = CellFrame("", "transparent", font_size)
                        self.setCellWidget(new_row, col, frame)
                        frame.setMinimumSize(inner_size, inner_size)
                        frame.setMaximumSize(inner_size, inner_size)
                    self.setRowHeight(new_row, cell_size)
                    self.setCurrentCell(new_row, 0)
                    self.prev_focused_cell = (new_row, 0)
                    print(f"Enter: row={new_row}, col=0, prev_focused={self.prev_focused_cell}")
            return

        # Backspace: Only in final row, delete empty row in first column
        if (
            key == Qt.Key.Key_Backspace
            and current_row >= 0
            and current_col >= 0
            and current_row == self.rowCount() - 1
        ):
            frame = self.cellWidget(current_row, current_col)
            # Check if row is empty
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
                print(f"Backspace delete: row={new_row}, col={new_col}, prev_focused={self.prev_focused_cell}")
            else:
                if frame:
                    frame.setText("")
                    frame.setBackground("transparent")
                    # Update font size
                    viewport_width = self.viewport().width()
                    cell_size = viewport_width // self.columnCount()
                    inner_size = cell_size - 2 - 10
                    font_size = int(inner_size * self.font_size_ratio)
                    frame.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
                    frame.updateStyle(current_row == self.currentRow() and current_col == self.currentColumn())
                    self.viewport().update()
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
        words = []
        clue_colors = []

        for row in range(self.rowCount() - 1):
            # self.setRowHeight(row, cell_size)
            word = ''.join(self.cellWidget(row, c).text() for c in range(self.columnCount()))
            words.append(word)
            colors = tuple(self.cellWidget(row, c).bg_color for c in range(self.columnCount()))
            clue_colors.append(colors)

        return words, clue_colors

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Word Table Test")
        self.setGeometry(100, 100, 600, 400)

        # Central widget and layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top layout for table and list
        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)

        # Word table
        self.table = WordTableWidget(rows=1, cols=5, parent=self)
        top_layout.addWidget(self.table)

        # List widget for testing
        self.list_widget = QListWidget(self)
        # Add sample words
        for word in ["hello", "world", "hi", "hi123", "toolongword"]:
            self.list_widget.addItem(QListWidgetItem(word))
        self.list_widget.setMaximumWidth(150)
        top_layout.addWidget(self.list_widget)

        # Virtual keyboard
        keyboard_widget = QWidget(self)
        keyboard_layout = QGridLayout(keyboard_widget)
        keyboard_layout.setSpacing(5)
        letters = list(ascii_uppercase)
        button_size = 40
        positions = [
            (0, i) for i in range(10)
        ] + [
            (1, i) for i in range(9)
        ] + [
            (2, i) for i in range(7)
        ]
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
        keyboard_layout.addWidget(enter_button, 2, 7)
        back_button = QPushButton("BACK", keyboard_widget)
        back_button.setFixedSize(60, button_size)
        back_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        keyboard_layout.addWidget(back_button, 2, 8)
        reset_button = QPushButton("RESET", keyboard_widget)
        reset_button.setFixedSize(60, button_size)
        reset_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        keyboard_layout.addWidget(reset_button, 2, 9)
        main_layout.addWidget(keyboard_widget)

        # Connect signals
        self.list_widget.itemClicked.connect(self.table.onListItemSelected)
        self.table.wordSubmitted.connect(self.onWordSubmitted)
        self.table.wordWithdrawn.connect(self.onWordWithdrawn)
        for letter, button in self.buttons.items():
            button.clicked.connect(self.table.onVirtualKeyPressed)
        enter_button.clicked.connect(self.table.onVirtualKeyPressed)
        back_button.clicked.connect(self.table.onVirtualKeyPressed)
        reset_button.clicked.connect(self.table.clear)

    def onWordSubmitted(self, word, colors):
        """Slot to handle wordSubmitted signal."""
        print(f"Received wordSubmitted: word='{word}', colors={colors}")

    def onWordWithdrawn(self):
        print(f"Received wordWithdrawn")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
