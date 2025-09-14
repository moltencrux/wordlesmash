import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication
from .main_window import MainWordLeSmashWindow
from .ui.wordlesmash_rc import qInitResources

logger = logging.getLogger(__name__)

QCoreApplication.setApplicationName('WordLeSmash')
QCoreApplication.setOrganizationName('moltencrux')

qInitResources()

def main():
    """Entry point for running the WordLeSmash application."""
    logger.debug('__main__.py: starting')
    app = QApplication(sys.argv)
    window = MainWordLeSmashWindow()
    window.show()
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())
