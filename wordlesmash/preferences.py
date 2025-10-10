from PyQt6.QtCore import (Qt, pyqtSlot, QModelIndex, QAbstractListModel,
    QSortFilterProxyModel, QVariant, QTimer, QEvent, QItemSelection
)
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
    QItemDelegate, QListWidgetItem, QMessageBox, QTreeWidgetItem, QListView,
    QApplication
)
from PyQt6.QtGui import QIcon, QCloseEvent
from .ui_loader import load_ui_class, UI_CLASSES, pathhelper
from .solver import DecisionTreeGuessManager
from .dialogs import ProgressDialog, BatchAddDialog, NewProfileDialog
from .delegates import (MultiBadgeDelegate, PicksDelegate, CandidatesDelegate,
    InitialPickValidator, CandidateValidator, PickValidator
)
from .profile_manager import Profile
from .wordle_game import Color
from .workers import DecisionTreeRoutesGetter
from .models import PicksModel, CandidatesProxy, ValidatedProxy
import logging
import time

logger = logging.getLogger(__name__)

Ui_preferences = load_ui_class(*UI_CLASSES['MainPreferences'])

class MainPreferences(QDialog, Ui_preferences):
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("MainPreferences.__init__ started")
        self.profile_manager = parent.profile_manager
        self.word_length = 5
        self.guess_manager = None
        self.default_icon = QIcon.fromTheme("emblem-default", QIcon())  # Fallback to empty icon
        self.initUI()
        self.loadSettings()
        logger.debug("MainPreferences.__init__ completed")

    def initUI(self):
        start = time.time()
        self.setupUi(self)
        logger.debug(f"initUI: QComboBox item count before clear: {self.profileComboBox.count()}")
        self.profileComboBox.clear()
        logger.debug(f"initUI: QComboBox item count after clear: {self.profileComboBox.count()}")
        self.profileComboBox.setEditable(True)
        self.profileComboBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.removeInitialPickButton.clicked.connect(self.removeInitialPick)
        self.removePickButton.clicked.connect(self.removePick)
        self.removeCandidateButton.clicked.connect(self.removeCandidate)
        self.addProfileButton.clicked.connect(self.addProfile)
        self.removeProfileButton.clicked.connect(self.removeProfile)
        self.setDefaultProfileButton.clicked.connect(self.setDefaultProfile)
        self.copyProfileButton.clicked.connect(self.copyProfile)
        self.removeTreeButton.clicked.connect(self.moveDecisionTreeToInitialPick)
        self.exploreTreeButton.clicked.connect(self.onExploreTreeButtonClicked)
        self.manageCandidatesDialog = BatchAddDialog(self, word_length=self.word_length, title="Batch Add Candidates")
        self.managePicksDialog = BatchAddDialog(self, word_length=self.word_length, title="Batch Add Picks")
        self.manageCandidatesButton.clicked.connect(self.onManageCandidates)
        self.managePicksButton.clicked.connect(self.onManagePicks)
        profile = self.profile_manager.getCurrentProfile()
        self.picksList.blockSignals(True)
        self.candidatesList.blockSignals(True)
        self.picksList.setItemDelegate(PicksDelegate(self.word_length, profile, self.picksList))
        self.candidatesList.setItemDelegate(CandidatesDelegate(self.word_length, profile, self.candidatesList))
        self.picksList.setModel(profile.model)
        self.picksList.itemDelegate().closeEditor.connect(self.on_editor_closed)
        self.candidatesList.itemDelegate().closeEditor.connect(self.on_editor_closed)
        self.picksList.blockSignals(False)
        self.candidatesList.blockSignals(False)

        # Initialize chartTreeButton as disabled
        self.chartTreeButton.setEnabled(False)
        self.removeTreeButton.setEnabled(False)

        # Initialize decisionTreeList actions
        self.decisionTreeList.activated.connect(self.exploreTree)

        # Connect line editor signals
        self.initialPicksLineEdit.returnPressed.connect(self.addInitialPick)
        self.candidatesLineEdit.returnPressed.connect(self.addCandidate)
        self.picksLineEdit.returnPressed.connect(self.addPick)

        self.chartTreeButton.clicked.connect(self.onChartTreeButtonClicked)
        self.profileComboBox.activated.connect(self.onProfileChanged)
        self.gameTypeComboBox.currentTextChanged.connect(self.profile_manager.changeGameType)
        self.gameTypeComboBox.currentTextChanged.connect(self.profile_manager.changeGameType)
        # Tentatively disable unsupported game mode options
        self.gameTypeComboBox.model().item(1).setEnabled(False)
        self.gameTypeComboBox.model().item(2).setEnabled(False)
        self.buttonBox.accepted.connect(self.onOK)
        self.buttonBox.rejected.connect(self.onCancel)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.onApply)
        # Disable default button to prevent Enter key from accepting dialog
        # Question, could a custom dialog box be made to consume enter keyPressEvents?
        self.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setAutoDefault(False)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Apply).setAutoDefault(False)

        delegate = MultiBadgeDelegate(self.treeWidget, badge_size=32, radius=6, font_px=18, spacing=3, left_padding=0)
        self.treeWidget.setItemDelegateForColumn(0, delegate)
        self.treeWidget.setIndentation(35)
        logger.debug("MainPreferences.initUI: Installed event filter for initialPicksLineEdit")
        logger.debug("MainPreferences.initUI completed")

    def keyPressEvent(self, event):
        logger.debug(f"MainPreferences.keyPressEvent: key={event.key()}, focusWidget={self.focusWidget()}")
        if event.key() == Qt.Key.Key_Escape:
            logger.debug("Esc key pressed in MainPreferences, triggering close")
            self.close()
            return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.profileComboBox.hasFocus() or self.profileComboBox.lineEdit().hasFocus():
                self.renameProfile()
                event.accept()
                return
            # elif self.initialPicksLineEdit.hasFocus():
            #     logger.debug("MainPreferences.keyPressEvent: Enter pressed in initialPicksLineEdit, handling via addInitialPick")
            #     # self.addInitialPick()...
            #     event.accept() # Is this to prevent closing? why would we see it if the child gets it?
            #     return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if obj == self.profileComboBox.lineEdit():
                logger.debug("MainPreferences.eventFilter: Enter pressed in profileComboBox.lineEdit, renaming profile")
                self.renameProfile()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        logger.debug("MainPreferences.closeEvent triggered")
        if self.profile_manager.has_pending_changes():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Apply them?",
                QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Apply:
                self.onApply()
            elif reply == QMessageBox.StandardButton.Discard:
                self.onCancel()
            else:
                event.ignore()
                return
        super().closeEvent(event)

    def updateCountLabels(self):
        """Update candidateCountLabel and picksCountLabel with current counts."""
        self.picksCountLabel.setText(f"({self.picksList.model().rowCount()})")
        self.candidatesCountLabel.setText(f"({self.candidatesList.model().rowCount()})")
        logger.debug(f"updateCountLabels: picksList rowCount={self.picksList.model().rowCount()}, candidatesList rowCount={self.candidatesList.model().rowCount()}")

    def getUniqueProfileName(self, base_name):
        profile_names = self.profile_manager.getProfileNames()
        name = base_name
        counter = 1
        while name in profile_names:
            name = f"{base_name}_{counter}"
            counter += 1
        return name

    @pyqtSlot(QModelIndex, QModelIndex)
    def onInitialPicksListCurrentChanged(self, current: QModelIndex, previous: QModelIndex):
        self.chartTreeButton.setEnabled(current.isValid())

    @pyqtSlot(QModelIndex, QModelIndex)
    def onDecisionTreeListCurrentChanged(self, current: QModelIndex, previous: QModelIndex):
        self.removeTreeButton.setEnabled(current.isValid())


    @pyqtSlot()
    def onChartTreeButtonClicked(self):
        logger.debug("onChartTreeButtonClicked started")
        selected_index = next(iter(self.initialPicksList.selectedIndexes()), None)
        # selected_indexes = self.initialPicksList.selectedIndexes()
        model = self.initialPicksList.model()

        if not selected_index:
            logger.debug("No word selected for decision tree generation")
            return

        # selected_index = next(iter(selected_indexes), None)
        pick = model.data(selected_index)

        # Check if an editor is open and retrieve its text
        if not pick:
            logger.debug("Empty word selected for decision tree generation")
            QMessageBox.warning(self, "Invalid Word", "The selected word is empty or invalid.")
            return
        profile_name = self.profile_manager.getCurrentProfileName()
        logger.debug(f"Generating decision tree for word: '{pick}' in profile: '{profile_name}'")
        self.spawnDecisionTreeRoutesGetter(pick)

    @pyqtSlot()
    def moveDecisionTreeToInitialPick(self, text=None):
        text = self.removeDecisionTree()
        if text is not None:
            new_model_index = self.profile_manager.addInitialPick(text)
            self.initialPicksList.scrollTo(new_model_index, QListView.ScrollHint.PositionAtBottom)
            self.initialPicksList.setCurrentIndex(new_model_index)
            logger.debug(f"Re-added text '{text}' to initialPicksList")

    @pyqtSlot()
    def removeDecisionTree(self, text=None):
        if not text:
            model = self.decisionTreeList.model()
            selected_index = next(iter(self.decisionTreeList.selectedIndexes()), None)
            if not selected_index:
                logger.debug("No decision tree selected")
                return
            text = model.data(selected_index)

        self.profile_manager.removeDecisionTree(text)
        return text

    def loadSettings(self):
        logger.debug("MainPreferences.loadSettings started")
        self.populateProfiles()
        current_profile = self.profile_manager.getCurrentProfileName()
        logger.debug(f"loadSettings: current_profile='{current_profile}'")
        if current_profile:
            index = self.profileComboBox.findData(current_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
                self.loadProfileSettings(index)
        logger.debug("MainPreferences.loadSettings completed")

    @pyqtSlot(int)
    def loadProfileSettings(self, index: int):
        logger.debug(f"loadProfileSettings: index={index}")
        if index < 0:
            logger.debug("loadProfileSettings: Invalid index")
            return
        name = self.profileComboBox.itemData(index, Qt.ItemDataRole.UserRole)
        if not name:
            logger.debug(f"No valid profile name at index {index}")
            return
        logger.debug(f"Loading profile settings for: '{name}'")
        self.profile_manager.setCurrentProfile(name)
        self.setListModels()
        self.updateDelegates()
        self.updateEditors()
        self.treeWidget.clear()
        logger.debug(f"Loaded profile settings: '{name}', word_length={self.word_length}, "
                    f"initial_picks={self.initialPicksList.model().rowCount()}, "
                    f"picks={self.picksList.model().rowCount()}, "
                    f"candidates={self.candidatesList.model().rowCount()}")

    def setListModels(self):
        logger.debug("MainPreferences.setListModels started")
        profile = self.profile_manager.getCurrentProfile()
        self.word_length = profile.word_length
        logger.debug(f"setListModels: profile.picks={profile.picks}, profile.candidates={profile.candidates}")
        self.initialPicksList.setModel(profile.initial_picks)
        self.initialPicksList.selectionModel().currentChanged.connect(self.onInitialPicksListCurrentChanged)
        self.decisionTreeList.setModel(profile.dt_model)
        self.decisionTreeList.selectionModel().currentChanged.connect(self.onDecisionTreeListCurrentChanged)
        candidates_proxy = CandidatesProxy()
        candidates_proxy.setSourceModel(profile.model)
        self.candidatesList.setModel(candidates_proxy)
        candidates_proxy.rowsInserted.connect(self.updateCountLabels)
        candidates_proxy.rowsRemoved.connect(self.updateCountLabels)
        candidates_proxy.modelReset.connect(self.updateCountLabels)
        self.picksList.setModel(profile.model) # no proxy for picks
        profile.model.rowsInserted.connect(self.updateCountLabels)
        profile.model.rowsRemoved.connect(self.updateCountLabels)
        profile.model.modelReset.connect(self.updateCountLabels)
        self.updateCountLabels()
        logger.debug(f"picksList rowCount after population: {self.picksList.model().rowCount()}")
        logger.debug("MainPreferences.setListModels completed")

    @pyqtSlot(int)
    def onProfileChanged(self, index: int):
        """Handle profile switch via profileComboBox.activated signal."""
        QApplication.processEvents()   # lets the profileComboBox repaint loading

        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)

        self.setDisabled(True)
        # self.profileComboBox.update()
        # I want to put up a busy dialog here, but loadProfile() blocks
        logger.debug(f"onProfileChanged: index={index}")
        self.loadProfileSettings(index)
        # XXX why did we do this? I think this was when profile changes were committed immediately
        # self.parent().resetGuessManager()
        self.setEnabled(True)
        QApplication.restoreOverrideCursor()
        logger.debug(f"Profile changed to index {index}, reset guess_manager")

    @pyqtSlot()
    def onApply(self):
        logger.debug("onApply started")
        self.profile_manager.commitChanges()
        self.populateProfiles()
        # self.parent().resetGuessManager()
        logger.debug("onApply completed")

    def updateDelegates(self):
        logger.debug("updateDelegates started")
        profile = self.profile_manager.getCurrentProfile()
        delegate_picks = PicksDelegate(self.word_length, profile, self.picksList)
        self.picksList.setItemDelegate(delegate_picks)
        delegate_candidates = CandidatesDelegate(self.word_length, profile, self.candidatesList)
        self.candidatesList.setItemDelegate(delegate_candidates)
        logger.debug("updateDelegates completed")
        delegate_candidates.closeEditor.connect(self.on_editor_closed)
        delegate_picks.closeEditor.connect(self.on_editor_closed)

    def updateEditors(self):
        profile = self.profile_manager.getCurrentProfile()

        initPickValidator = InitialPickValidator(self.word_length, profile, self.initialPicksLineEdit)
        self.initialPicksLineEdit.setValidator(initPickValidator)
        init_picks_completer_proxy = ValidatedProxy(initPickValidator)
        init_picks_completer_proxy.setSourceModel(profile.model)
        self.initialPicksLineEdit.setCompleterModel(init_picks_completer_proxy)

        candidateValidator = CandidateValidator(self.word_length, profile, self.candidatesLineEdit)
        self.candidatesLineEdit.setValidator(candidateValidator)
        candidate_completer_proxy = ValidatedProxy(candidateValidator)
        candidate_completer_proxy.setSourceModel(profile.model)
        self.candidatesLineEdit.setCompleterModel(candidate_completer_proxy)

        pickValidator = PickValidator(self.word_length, profile, self.picksLineEdit)
        self.picksLineEdit.setValidator(pickValidator)
 
    @pyqtSlot()
    def renameProfile(self):
        # XXX probably should move most of this logic into the profile manager.
        # It's also probably broken with handling of picks/candidates and syncToProfile

        logger.debug("renameProfile started")
        current_profile = self.profile_manager.getCurrentProfileName()
        new_name = self.profileComboBox.currentText().strip()
        if new_name and new_name != current_profile:
            profile = self.profile_manager.renameProfile(current_profile, new_name)

            self.populateProfiles() # XXX does this incorporate the newly named one?
            index = self.profileComboBox.findData(new_name, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
                self.profile_manager.setCurrentProfile(new_name) # XXX i feel this is not enough
        logger.debug("renameProfile completed")

    @pyqtSlot()
    def removeProfile(self):
        logger.debug("removeProfile started")
        current_profile = self.profile_manager.getCurrentProfileName()
        if current_profile:
            reply = QMessageBox.question(
                self, "Remove Profile?",
                f"Remove profile <b>{current_profile}</b>?",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Ok:
                self.profile_manager.deleteProfile(current_profile)
                self.populateProfiles()
        logger.debug("removeProfile completed")

    @pyqtSlot()
    def removePick(self):
        selected_index = self.picksList.currentIndex()
        self.setDisabled(True)
        model = self.picksList.model()
        model.rowsInserted.connect(lambda: self.setEnabled(True))
        model.rowsRemoved.connect(lambda: self.setEnabled(True))
        model.modelReset.connect(lambda: self.setEnabled(True))
        self.profile_manager.removePick(selected_index)

    @pyqtSlot()
    def addInitialPick(self, text=None):
        text = text if text is not None else self.initialPicksLineEdit.text()
        # model = self.initialPicksList.model()
        if self.confirmInitialPick(text):
            new_model_index = self.profile_manager.addInitialPick(text)
            self.initialPicksList.scrollTo(new_model_index, QListView.ScrollHint.PositionAtBottom)
            self.initialPicksList.setCurrentIndex(new_model_index)
            self.initialPicksLineEdit.clear()


    def confirmInitialPick(self, text) -> QMessageBox.StandardButton:
        profile = self.profile_manager.getCurrentProfile()

        if text and text in profile.model:
            return True

        reply = QMessageBox.question(
            self.window(),
            "Add to Picks?",
            f"'{text}' is not in the legal picks. Add it to the picks list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No 
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.profile_manager.addPick(text)
            return True

        return False

    @pyqtSlot()
    def onOK(self):
        logger.debug("onOK started")
        self.onApply()
        self.parent().resetGuessManager()
        # self.parent().spawnSuggestionGetter()
        self.accept()
        logger.debug("onOK completed")

    @pyqtSlot()
    def onCancel(self):
        logger.debug("onCancel started")
        self.profile_manager.discardChanges()
        self.loadSettings() # or maybe on show?
        self.reject()
        logger.debug("onCancel completed")

    @pyqtSlot()
    def addPick(self):
        text = self.picksLineEdit.text()
        new_model_index = self.profile_manager.addPick(text)
        self.picksList.scrollTo(new_model_index, QListView.ScrollHint.PositionAtBottom)
        self.picksList.setCurrentIndex(new_model_index)
        self.picksLineEdit.clear()

    def addCandidate(self):
        text = self.candidatesLineEdit.text()
        raw_model_index = self.profile_manager.addCandidate(text)
        proxy = self.candidatesList.model()
        new_model_index = proxy.mapFromSource(raw_model_index)
        self.candidatesList.scrollTo(new_model_index, QListView.ScrollHint.PositionAtBottom)
        self.candidatesList.setCurrentIndex(new_model_index)
        self.candidatesLineEdit.clear()

    @pyqtSlot()
    def removeInitialPick(self, text=None):
        logger.debug("removeInitialPick started")

        if text:
            model = self.initialPicksList.model()
            matches = model.match(model.index(0,0), Qt.ItemDataRole.DisplayRole, text, hits=-1, flags=Qt.MatchFlag.MatchExactly)
            index_to_remove = next(iter(matches), None)
        else:
            index_to_remove = next(iter(self.initialPicksList.selectedIndexes()), None)

        if index_to_remove:
            self.profile_manager.removeInitialPick(index_to_remove)

        logger.debug("removeInitialPick completed")

    @pyqtSlot()
    def setDefaultProfile(self):
        logger.debug("setDefaultProfile started")
        current_profile = self.profile_manager.getCurrentProfileName()
        if current_profile:
            self.profile_manager.setDefaultProfile(current_profile)
            self.populateProfiles()
        logger.debug("setDefaultProfile completed")

    @pyqtSlot()
    def removeCandidate(self):
        selected_index = self.candidatesList.currentIndex()
        self.profile_manager.removeCandidate(selected_index)

    @pyqtSlot()
    def addProfile(self):
        logger.debug("addProfile started")
        dialog = NewProfileDialog(self)
        if dialog.exec():
            name = dialog.nameEdit.text().strip()
            if name:
                profile = self.profile_manager.modifyProfileWords(name)
                self.populateProfiles()
                index = self.profileComboBox.findData(name, Qt.ItemDataRole.UserRole)
                if index >= 0:
                    self.profileComboBox.setCurrentIndex(index)

                match dialog.startingWordsComboBox.currentText():
                    case "NYT basic word list":

                        candidates_file = pathhelper('wordle_candidates.txt', package='wordlesmash.words')
                        with candidates_file.open("r", encoding="utf-8") as f:
                            candidates = sorted(line.strip().upper() for line in f if line.strip())  # Pre-sort
                        profile.model.batch_add_candidates(candidates)

                        picks_file = pathhelper('wordle_picks.txt', package='wordlesmash.words')
                        with picks_file.open("r", encoding="utf-8") as f:
                            picks = sorted(line.strip().upper() for line in f if line.strip())  # Pre-sort
                        profile.model.batch_add_picks(picks)

                self.onProfileChanged(index)

        logger.debug("addProfile completed")

    @pyqtSlot()
    def copyProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            logger.debug("No profile selected to copy")
            QMessageBox.warning(self, "No Profile Selected", "Please select a profile to copy.")
            return
        source_profile = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        new_name = self.getUniqueProfileName(f"Copy of {source_profile}")
        logger.debug(f"Copying profile {source_profile} to {new_name}")
        profile = self.profile_manager.loadProfile(source_profile)
        profile.dirty = True
        self.profile_manager.modified[new_name] = profile
        self.profile_manager.setCurrentProfile(new_name)
        self.profileComboBox.blockSignals(True)
        try:
            self.profileComboBox.addItem(new_name, userData=new_name)
            index = self.profileComboBox.count() - 1
            self.profileComboBox.setCurrentIndex(index)
            default_profile = self.profile_manager.getDefaultProfile()
            self.profileComboBox.setItemIcon(index, self.default_icon if new_name == default_profile else QIcon())
            logger.debug(f"Added copied profile {new_name} to QComboBox at index {index}")
        finally:
            self.profileComboBox.blockSignals(False)
        self.loadProfileSettings(self.profileComboBox.currentIndex())
        self.parent().statusBar.showMessage(f"Copied profile {source_profile} to {new_name}")
        self.is_modified = True

    def saveSettings(self):
        logger.debug("saveSettings started")
        self.syncToProfile(self.profile_manager.getCurrentProfileName())
        self.profile_manager.commitChanges()
        logger.debug("saveSettings completed")

    def onManagePicks(self):

        logger.debug("onManagePicks started")
        model = self.picksList.model()
        original_words = sorted(word for word in model.get_picks() if word)
        logger.debug(f"onManagePicks Passing words to dialog: {len(original_words)} picks")
        dialog = BatchAddDialog(self, words=original_words, word_length=self.word_length, title="Batch Add Picks")
        if dialog.exec():
            self.profile_manager.batchAddPicks(dialog.valid_words)
        logger.debug("onManagePicks completed")

    @pyqtSlot()
    def onManageCandidates(self):
        logger.debug("onManageCandidates started")
        model = self.candidatesList.model().sourceModel()
        original_words = sorted(word for word in model.get_candidates() if word)
        logger.debug(f"onManageCandidates: Passing words to dialog: {len(original_words)} candidates")
        dialog = BatchAddDialog(self, words=original_words, word_length=self.word_length, title="Batch Add Candidates")
        if dialog.exec():
            self.profile_manager.batchAddCandidates(dialog.valid_words)
        logger.debug("onManageCandidates completed")

    @pyqtSlot()
    def on_editor_closed(self):
        # self.addPickButton.setEnabled(True)
        # self.addCandidateButton.setEnabled(True)
        self.updateCountLabels()
        logger.debug("on_editor_closed: Re-enabled addPickButton and addCandidateButton")


    def spawnDecisionTreeRoutesGetter(self, pick):
        """Start a DecisionTreeRoutesGetter thread to generate a decision tree for the given pick."""
        logger.debug(f"spawnDecisionTreeRoutesGetter: pick='{pick}'")
        parent = self.parent()
        parent.statusBar.showMessage(f"Generating decision tree for {pick}...")

        # Create a thread that will launch a search
        self.chartTreeButton.setDisabled(True)
        if self.guess_manager is None:
            profile = self.profile_manager.getCurrentProfile()
            self.guess_manager = DecisionTreeGuessManager(
                profile.model.get_picks(),
                profile.model.get_candidates(),
                length=profile.word_length,
                cache_path=self.profile_manager.app_cache_path()
            )
            logger.debug(f"Created new DecisionTreeGuessManager for pick: '{pick}'")
        getter = DecisionTreeRoutesGetter(self.profile_manager, pick, self.guess_manager, self)
        progress_dialog = ProgressDialog(self, cancel_callback=getter.stop)
        # getter.ready.connect(self.updateDecisionTrees)
        getter.ready.connect(self.profile_manager.addDecisionTree)
        # why not just connect it directly to the profile or profile manager?
        # XXX
        getter.finished.connect(progress_dialog.close)
        progress_dialog.show()
        getter.start()


    @staticmethod
    def create_tree_widget_items_it(data_dict):
        """
        Iteratively creates QTreeWidgetItem hierarchy from a dictionary.

        :param data_dict: The dictionary to convert into QTreeWidgetItems.
                          Expected top-level: {pick: clue_dict}
                          where pick is an iterable of chars and clue_dict is {clue: value}
        :return: The root QTreeWidgetItem if parent was None, otherwise None.
        """
        color_hex_map = {
            Color.BLACK: "#000000",
            Color.YELLOW: "#c9b458",
            Color.GREEN: "#6aaa64",
            Color.UNKNOWN: "transparent"
        }

        root_item = QTreeWidgetItem()
        pick, clue_dict = next(iter(data_dict.items()))
        root_item.setText(0, pick)
        stack = [(root_item, data_dict)]
        end = []

        # Create the item tree structure and set the clue colors of each item
        while stack:
            parent, dt = stack.pop()
            end.append(parent)
            pick, clue_dict = next(iter(dt.items()))
            for clue, new_dt in sorted(clue_dict.items()):
                item = QTreeWidgetItem(parent)
                user_data = ','.join(f'{color_hex_map[c]}' for char, c in zip(pick, clue))
                item.setText(0, pick)
                item.setData(0, Qt.ItemDataRole.UserRole, user_data)
                if new_dt is not None:
                    stack.append((item, new_dt))
                else:
                    item.setText(1, '1') # Leaves have value 1

        # Sum the number of leaf decendents under each item
        for item in reversed(end):
            child_leaves = sum(int(item.child(i).text(1)) for i in range(item.childCount()))
            item.setText(1, str(child_leaves))

        return root_item

    def onExploreTreeButtonClicked(self):
        selected_index = next(iter(self.decisionTreeList.selectedIndexes()), None)
        self.exploreTree(selected_index)


    @pyqtSlot(QModelIndex)
    def exploreTree(self, index: QModelIndex):
        logger.debug("exploreTree started")
        # self.decisionTreeList.reset()
        self.treeWidget.clear()
        if not index.isValid():
            logger.debug("No word selected for decision tree generation")
            return

        model = self.decisionTreeList.model()

        # Check if an editor is open and retrieve its text
        profile = self.profile_manager.getCurrentProfile()
        word = model.data(index)
        if word not in profile.dt or profile.dt[word] is None:
            logger.debug(f"No valid decision tree for '{word}'")
            return
        tree = {word: profile.dt[word]}
        tree_widget_item = self.create_tree_widget_items_it(tree)
        self.treeWidget.addTopLevelItem(tree_widget_item)
        tree_widget_item.setExpanded(True)
        logger.debug("exploreTree completed")

    def populateProfiles(self):
        logger.debug("populateProfiles started")
        self.profileComboBox.clear()
        current_profile = self.profile_manager.getCurrentProfileName()
        default_profile = self.profile_manager.getDefaultProfile()
        for name in sorted(self.profile_manager.getProfileNames()):
            self.profileComboBox.addItem(name, userData=name)
            if name == default_profile:
                index = self.profileComboBox.findData(name, Qt.ItemDataRole.UserRole)
                if index >= 0:
                    self.profileComboBox.setItemIcon(index, self.default_icon)
        if current_profile:
            index = self.profileComboBox.findData(current_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
        logger.debug("populateProfiles completed")
