import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication
from .main_window import MainWordLeSmashWindow
from .ui.wordlesmash_rc import qInitResources

logging.basicConfig(level=logging.DEBUG if __debug__ else logging.ERROR, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

QCoreApplication.setApplicationName('WordLeSmash')
QCoreApplication.setOrganizationName('moltencrux')

qInitResources()

def main():
    """Entry point for running the WordLeSmash application."""
    app = QApplication(sys.argv)
    window = MainWordLeSmashWindow()
    window.show()
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())