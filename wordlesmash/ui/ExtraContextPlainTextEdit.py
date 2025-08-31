from PyQt6.QtWidgets import QPlainTextEdit, QMenu, QApplication
from PyQt6.QtGui import QAction



class ExtraContextPlainTextEdit(QPlainTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # List to hold extra context menu actions
        self.extraContextActions = []

    def contextMenuEvent(self, event):
        # Create a context menu
        context_menu = self.createStandardContextMenu()

        # Add extra actions from self.extraContextActions
        context_menu.addActions(self.extraContextActions)

        # Show the context menu at the cursor position
        context_menu.exec(event.globalPos())

# Example usage
if __name__ == "__main__":
    import os
    import sys

    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.append(parent_dir)

    app = QApplication(sys.argv)

    # Create an instance of the custom text edit
    text_edit = ExtraContextPlainTextEdit()
    text_edit.setWindowTitle("Custom QPlainTextEdit Example")
    text_edit.resize(400, 300)

    # Add extra context actions
    action1 = QAction("Extra Action 1", text_edit)
    action1.triggered.connect(lambda: print("Extra Action 1 triggered"))
    text_edit.extraContextActions.append(action1)

    action2 = QAction("Extra Action 2", text_edit)
    action2.triggered.connect(lambda: print("Extra Action 2 triggered"))
    text_edit.extraContextActions.append(action2)

    text_edit.show()
    sys.exit(app.exec())

