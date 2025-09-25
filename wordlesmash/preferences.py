from PyQt6.QtCore import Qt, pyqtSlot, QModelIndex, QAbstractListModel, QSortFilterProxyModel, QVariant, QTimer, QEvent
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
    QItemDelegate, QListWidgetItem, QMessageBox, QTreeWidgetItem, QListView
)
from PyQt6.QtGui import QIcon, QCloseEvent
from .ui_loader import load_ui_class, UI_CLASSES
from .solver import DecisionTreeGuessManager
from .dialogs import ProgressDialog, BatchAddDialog, NewProfileDialog
from .delegates import UpperCaseDelegate, MultiBadgeDelegate, PicksDelegate, CandidatesDelegate, InitialPickValidator, CandidateValidator, PickValidator
from .profile_manager import Profile # , ProfileManager
from .wordle_game import Color
from .workers import DecisionTreeRoutesGetter
from .models import PicksModel, CandidatesProxy, AlphabeticProxy, FilterProxy, ValidatedProxy
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
        self.removeTreeButton.clicked.connect(self.removeDecisionTree)
        self.exploreTreeButton.clicked.connect(self.exploreTree)
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

        self.initialPicksList.itemSelectionChanged.connect(self.onInitialPicksListSelectionChanged)

        # Connect line editor signals
        self.initialPicksLineEdit.returnPressed.connect(self.addInitialPick)
        self.candidatesLineEdit.returnPressed.connect(self.addCandidate)
        self.picksLineEdit.returnPressed.connect(self.addPick)

        self.chartTreeButton.clicked.connect(self.onChartTreeButtonClicked)
        self.profileComboBox.activated.connect(self.onProfileChanged)
        self.gameTypeComboBox.currentTextChanged.connect(self.profile_manager.changeGameType)
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

    def syncToProfile(self, profile_name: str) -> None:
        logger.debug(f"syncToProfile: profile_name={profile_name}")
        profile = self.profile_manager.modifyProfile(profile_name)
        # XXX why do we do this? would it not already be synced?
        # Actually, nothing happens on add ex adding to list, so sth needs to happpen
        # but maybe the model should be linked, synced or sth.
        profile.initial_picks = {self.initialPicksList.item(i).text() for i in range(self.initialPicksList.count()) if self.initialPicksList.item(i).text().strip()}
        profile.dirty = True
        profile.words_modified = True
        return profile

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
        # self.initialPicksCountLabel.setText(f"({self.initialPicksList.count()})")
        self.picksCountLabel.setText(f"({self.picksList.model().rowCount()})")
        self.candidatesCountLabel.setText(f"({self.candidatesList.model().rowCount()})")
        # self.decisionTreeCountLabel.setText(f"({self.decisionTreeList.count()})")
        logger.debug(f"updateCountLabels: picksList rowCount={self.picksList.model().rowCount()}, candidatesList rowCount={self.candidatesList.model().rowCount()}")

    def getUniqueProfileName(self, base_name):
        profile_names = self.profile_manager.getProfileNames()
        name = base_name
        counter = 1
        while name in profile_names:
            name = f"{base_name}_{counter}"
            counter += 1
        return name

    @pyqtSlot()
    def onInitialPicksListSelectionChanged(self):
        selected_items = self.initialPicksList.selectedItems()
        self.chartTreeButton.setEnabled(bool(selected_items))

    @pyqtSlot()
    def onChartTreeButtonClicked(self):
        logger.debug("onChartTreeButtonClicked started")
        selected_items = self.initialPicksList.selectedItems()
        if not selected_items:
            logger.debug("No word selected for decision tree generation")
            return
        # Check if an editor is open for the selected item
        selected_item = selected_items[0]
        selected_index = self.initialPicksList.indexFromItem(selected_item)
        # Check if an editor is open and retrieve its text
        editor_text = None
        if self.initialPicksList.isPersistentEditorOpen(selected_item):
            logger.debug("Editor open for selected item, retrieving text")
            editor = self.initialPicksList.itemWidget(selected_item)
            if isinstance(editor, QLineEdit):
                editor_text = editor.text().strip().upper()
                logger.debug(f"Editor text: '{editor_text}'")
        if editor_text:
            if not self.validateInitialPick(editor_text):
                logger.debug(f"Invalid editor text: '{editor_text}'")
                QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
                self.initialPicksList.closePersistentEditor(selected_item)
                self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                # self.addInitialPickButton.setEnabled(True)
                return
            legal_picks = {self.picksList.model().data(self.picksList.model().index(i, 0), Qt.ItemDataRole.DisplayRole) for i in range(self.picksList.model().rowCount())}
            if editor_text not in legal_picks:
                reply = QMessageBox.question(
                    self, "Add to Picks?",
                    f"'{editor_text}' is not in the legal picks. Add it to picks.txt?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    # XXX does this happen in the right order?
                    self.picks_model.add_pick(editor_text)
                    self.syncToProfile(self.profile_manager.getCurrentProfileName())
                    profile = self.profile_manager.getCurrentProfile()
                    profile.picks.add(editor_text)
                    profile.dirty = True
                    self.updateCountLabels()
                else:
                    logger.debug(f"User declined to add '{editor_text}' to picks")
                    self.initialPicksList.closePersistentEditor(selected_item)
                    self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                    # self.addInitialPickButton.setEnabled(True)
                    return
            self.initialPicksList.closePersistentEditor(selected_item)
            # self.addInitialPickButton.setEnabled(True)
        pick = selected_item.text().split(" (")[0].strip()
        if not pick:
            logger.debug("Empty word selected for decision tree generation")
            QMessageBox.warning(self, "Invalid Word", "The selected word is empty or invalid.")
            return
        profile_name = self.profile_manager.getCurrentProfileName()
        logger.debug(f"Generating decision tree for word: '{pick}' in profile: '{profile_name}'")
        self.spawnDecisionTreeRoutesGetter(pick)

    @pyqtSlot(str, bool)
    def updateDecisionTrees(self, pick: str, success: bool):
        """Update decisionTreeList and initialPicksList after DecisionTreeRoutesGetter finishes."""
        logger.debug(f"updateDecisionTrees: pick='{pick}', success={success}")
        if success:
            self.decisionTreeList.clear()
            profile = self.profile_manager.getCurrentProfile()
            for word in sorted(profile.dt.keys()):
                self.decisionTreeList.addItem(word)
            self.removeInitialPick(pick)
            self.updateCountLabels()
        self.chartTreeButton.setEnabled(True)

    @pyqtSlot()
    def removeDecisionTree(self):
        """Remove the selected decision tree, re-add its word to initialPicksList, and mark profile as modified."""
        logger.debug("removeDecisionTree started")
        selected_item = next(iter(self.decisionTreeList.selectedItems()), None)
        if not selected_item:
            logger.debug("No decision tree selected for removal")
            return
        word = selected_item.text()
        profile_name = self.profile_manager.getCurrentProfileName()
        self.profile_manager.removeDecisionTree(profile_name, word)
        # Remove from decisionTreeList
        self.decisionTreeList.takeItem(self.decisionTreeList.row(selected_item))
        # Re-add word to initialPicksList if not already present
        if not any(self.initialPicksList.item(i).text() == word for i in range(self.initialPicksList.count())):
            item = QListWidgetItem(word)
            self.initialPicksList.addItem(item)
            logger.debug(f"Re-added word '{word}' to initialPicksList")
        self.syncToProfile(self.profile_manager.getCurrentProfileName())
        profile = self.profile_manager.getCurrentProfile()
        if word not in profile.initial_picks:
            profile.initial_picks.add(word)
            profile.words_modified = True
            logger.debug(f"Added '{word}' to profile.initial_picks")
        self.updateCountLabels()

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
        self.populateLists()
        self.updateDelegates()
        self.updateEditors()
        logger.debug(f"Loaded profile settings: '{name}', word_length={self.word_length}, "
                    f"initial_picks={len(self.initialPicksList.findItems('*', Qt.MatchFlag.MatchWildcard))}, "
                    f"picks={self.picksList.model().rowCount()}, "
                    f"candidates={self.candidatesList.model().rowCount()}")

    def populateLists(self):
        logger.debug("MainPreferences.populateLists started")
        profile = self.profile_manager.getCurrentProfile()
        self.word_length = profile.word_length
        logger.debug(f"populateLists: profile.picks={profile.picks}, profile.candidates={profile.candidates}")
        self.initialPicksList.clear()
        for pick in profile.initial_picks:
            if pick.strip():
                item = QListWidgetItem(pick)
                self.initialPicksList.addItem(item)
                logger.debug(f"Added initial pick: '{pick}'")
        candidates_proxy = CandidatesProxy()
        candidates_proxy.setSourceModel(profile.model)
        self.candidatesList.setModel(candidates_proxy)
        self.picksList.setModel(profile.model) # no proxy for picks
        self.decisionTreeList.clear()
        for pick in profile.dt:
            self.decisionTreeList.addItem(pick)
        self.updateCountLabels()
        logger.debug(f"picksList rowCount after population: {self.picksList.model().rowCount()}")
        logger.debug("MainPreferences.populateLists completed")

    @pyqtSlot(int)
    def onProfileChanged(self, index: int):
        """Handle profile switch via profileComboBox.activated signal."""
        logger.debug(f"onProfileChanged: index={index}")
        self.loadProfileSettings(index)
        self.parent().resetGuessManager()
        logger.debug(f"Profile changed to index {index}, reset guess_manager")

    @pyqtSlot()
    def onApply(self):
        logger.debug("onApply started")
        self.syncToProfile(self.profile_manager.getCurrentProfileName())
        self.profile_manager.commitChanges()
        self.populateProfiles()
        self.parent().resetGuessManager()
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
            profile = self.profile_manager.modifyProfile(current_profile, new_name)

            ###profile.initial_picks = [self.initialPicksList.item(i).text() for i in range(self.initialPicksList.count())]
            profile.dirty = True
            profile.words_modified = True # necessary? maybe.. but shouldn't always need to recalc dtrees
            self.populateProfiles() # XXX does this incorporate the newly named one?
            index = self.profileComboBox.findData(new_name, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
                self.profile_manager.setCurrentProfile(new_name) # XXX i feel this is not enough
                # I think the profile maanger should take some real aciton here. verify later
        logger.debug("renameProfile completed")

    @pyqtSlot()
    def removeProfile(self):
        logger.debug("removeProfile started")
        current_profile = self.profile_manager.getCurrentProfileName()
        if current_profile:
           self.profile_manager.deleteProfile(current_profile)
           self.populateProfiles()
        logger.debug("removeProfile completed")

    @pyqtSlot(QListWidgetItem)
    def validateInitialPick(self, item):
        text = item.text().strip().upper() if isinstance(item, QListWidgetItem) else item.strip().upper()
        if len(text) != self.word_length or not text.isalpha():
            logger.debug(f"validateInitialPick failed: text='{text}'")
            return False
        logger.debug(f"validateInitialPick passed: text='{text}'")
        return True

    @pyqtSlot()
    def removePick(self):
        logger.debug("removePick started")
        picks_proxy = self.picksList.model()
        if hasattr(picks_proxy, 'sourceModel'):
            model = picks_proxy.sourceModel()
        else:
            model = picks_proxy

        selected_item = self.picksList.currentIndex()

        text = model.data(selected_item)

        if selected_item.isValid():
            source_row = picks_proxy.mapToSource(selected_item).row()
            if 0 <= source_row < model.rowCount():
                model.remove_pick_by_row(source_row)
                self.removeInitialPick(text)
                # XXX also remove DT
                picks_proxy.invalidate()
                # self.syncToProfile(self.profile_manager.getCurrentProfileName())
                self.updateCountLabels()

            else:
                logger.error(f"removePick Invalid source_row {source_row}, model_rows={self.picks_model.rowCount()}")
        logger.debug("removePick completed")

    @pyqtSlot()
    def addInitialPick(self, text=None):
        text = text if text is not None else self.initialPicksLineEdit.text()

        if self.confirmInitialPick(text):
            item = QListWidgetItem(text)
            self.initialPicksList.addItem(item)
            self.initialPicksLineEdit.clear()
            pass

    def confirmInitialPick(self, text) -> QMessageBox.StandardButton:
        profile = self.profile_manager.getCurrentProfile()

        # XXX this check is ugly, need a better way to check if the model contains a word
        if text and text in profile.model._items:
            return True

        reply = QMessageBox.question(
            self.window(),
            "Add to Picks?",
            f"'{text}' is not in the legal picks. Add it to the picks list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No 
        )

        if reply == QMessageBox.StandardButton.Yes:
            profile.model.add_pick(text)
            return True

        return False

    def handleEditorAction(self, action, text):
        """Handle InitialPicksLineEdit editorAction signal."""
        logger.debug(f"handleEditorAction: action={action}, text='{text}'")
        profile = self.profile_manager.getCurrentProfile()
        self.initialPicksList.blockSignals(True)
        try:
            if action == "yes":
                if text:
                    profile.model.add_pick(text)
                    item = QListWidgetItem(text)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable)
                    self.initialPicksList.addItem(item)
                    self.initialPicksList.scrollToBottom()
                    logger.debug(f"handleEditorAction: Added '{text}' to initialPicksList")
            elif action == "discard":
                logger.debug("handleEditorAction: Discarded input")
            else:  # continue
                logger.debug(f"handleEditorAction: Kept editor open with text '{text}'")
        finally:
            self.initialPicksList.blockSignals(False)



    @pyqtSlot()
    def onOK(self):
        logger.debug("onOK started")
        self.onApply()
        self.parent().resetGuessManager()
        self.parent().spawnSuggestionGetter()
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
        logger.debug("addPick started")
        model = self.picksList.model()
        new_model_index = model.add_pick()
        self.picksList.setCurrentIndex(new_model_index)
        self.picksList.scrollTo(new_model_index, QListView.ScrollHint.PositionAtBottom)

        try:
            self.picksList.edit(new_model_index)
        except Exception as e:
            logger.error(f"Failed to enter edit mode for picksList: {e}")
        # self.addPickButton.setEnabled(False)
        logger.debug(f"addPick: model.rowCount={model.rowCount()}")
        logger.debug("addPick completed")

    def addPick(self):
        profile = self.profile_manager.getCurrentProfile()
        text = self.picksLineEdit.text()
        # picks_model = self.picksList.model()
        new_model_index = profile.model.add_pick(text)
        self.picksList.scrollTo(new_model_index, QListView.ScrollHint.PositionAtBottom)
        self.picksList.setCurrentIndex(new_model_index)
        self.picksLineEdit.clear()

    def addCandidate(self):
        profile = self.profile_manager.getCurrentProfile()
        text = self.candidatesLineEdit.text()
        candidates_proxy = self.candidatesList.model()
        new_model_index = profile.model.add_candidate(text, candidates_proxy)
        self.candidatesList.scrollTo(new_model_index, QListView.ScrollHint.PositionAtBottom)
        self.candidatesList.setCurrentIndex(new_model_index)
        self.candidatesLineEdit.clear()

    @pyqtSlot()
    def removeInitialPick(self, text=None):
        logger.debug("removeInitialPick started")

        if text:
            matches = self.initialPicksList.findItems(text, Qt.MatchFlag.MatchExactly)
            item_to_remove = next(iter(matches), None)
        else:
            item_to_remove = next(iter(self.initialPicksList.selectedItems()), None)

        if item_to_remove:
            self.initialPicksList.takeItem(self.initialPicksList.row(item_to_remove))
            self.syncToProfile(self.profile_manager.getCurrentProfileName())
            self.updateCountLabels()
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
        logger.debug("removeCandidate started")
        candidates_proxy = self.candidatesList.model()
        model = candidates_proxy.sourceModel()
        selected_item = self.candidatesList.currentIndex()
        if selected_item.isValid():
            source_row = candidates_proxy.mapToSource(selected_item).row()
            if 0 <= source_row < model.rowCount():
                model.remove_candidate_by_row(source_row)
                candidates_proxy.invalidate()
                # self.syncToProfile(self.profile_manager.getCurrentProfileName())
                self.updateCountLabels()

            else:
                logger.error(f"removeCandidate: Invalid source_row {source_row}, model_rows={model.rowCount()}")
        logger.debug("removeCandidate completed")

    @pyqtSlot()
    def addProfile(self):
        logger.debug("addProfile started")
        dialog = NewProfileDialog(self)
        if dialog.exec():
            name = dialog.nameEdit.text().strip()
            if name:
                self.profile_manager.modifyProfile(name)
                self.populateProfiles()
                index = self.profileComboBox.findData(name, Qt.ItemDataRole.UserRole)
                if index >= 0:
                    self.profileComboBox.setCurrentIndex(index)
                self.profile_manager.setCurrentProfile(name)
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


    @pyqtSlot()
    def onManagePicks(self):
        logger.debug("onManagePicks started")
        profile = self.profile_manager.getCurrentProfile()
        model = self.picksList.model()
        original_words = sorted(word for word in model.get_picks() if word)
        logger.debug(f"onManagePicks: Passing words to dialog: {len(original_words)} picks")
        dialog = BatchAddDialog(self, words=original_words, word_length=self.word_length, title="Batch Add Picks")
        if dialog.exec():
            self.picksList.blockSignals(True)
            model.blockSignals(True)
            new_words = sorted(dialog.valid_words)
            for word in original_words:
                if word not in new_words:
                    model.remove_pick_by_text(word)
            model.batch_add_picks(new_words, is_candidate=False)
            model.blockSignals(False)
            self.picksList.blockSignals(False)
            self.syncToProfile(self.profile_manager.getCurrentProfileName())
            self.updateCountLabels()
            logger.debug(f"onManagePicks: Added {len(new_words)} picks, Removed {len([w for w in original_words if w not in new_words])} picks")
        logger.debug("onManagePicks completed")

    @pyqtSlot()
    def onManageCandidates(self):
        logger.debug("onManageCandidates started")
        profile = self.profile_manager.getCurrentProfile()
        model = self.candidatesList.model().sourceModel()
        original_words = sorted(word for word in model.get_candidates() if word)
        logger.debug(f"onManageCandidates: Passing words to dialog: {len(original_words)} candidates")
        dialog = BatchAddDialog(self, words=original_words, word_length=self.word_length, title="Batch Add Candidates")
        if dialog.exec():
            self.candidatesList.blockSignals(True)
            model.blockSignals(True)
            new_words = sorted(dialog.valid_words)
            for word in original_words:
                if word not in new_words:
                    model.remove_candidate_by_text(word)
            model.batch_add_candidates(new_words)
            model.blockSignals(False)
            self.candidatesList.blockSignals(False)
            self.syncToProfile(self.profile_manager.getCurrentProfileName())
            self.updateCountLabels()
            logger.debug(f"onManageCandidates: Added {len(new_words)} candidates, "
                        f"Removed {len([w for w in original_words if w not in new_words])} candidates")
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
        getter.ready.connect(self.updateDecisionTrees)
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
        root_item.setText(0, ','.join(pick))
        stack = [(root_item, data_dict)]
        end = []

        # Create the item tree structure and set the clue colors of each item
        while stack:
            parent, dt = stack.pop()
            end.append(parent)
            pick, clue_dict = next(iter(dt.items()))
            for clue, new_dt in sorted(clue_dict.items()):
                item = QTreeWidgetItem(parent)
                text = ','.join(f'{char}:{color_hex_map[c]}' for char, c in zip(pick, clue))
                item.setText(0, text)
                if new_dt is not None:
                    stack.append((item, new_dt))
                else:
                    item.setText(1, '1') # Leaves have value 1

        # Sum the number of leaf decendents under each item
        for item in reversed(end):
            child_leaves = sum(int(item.child(i).text(1)) for i in range(item.childCount()))
            item.setText(1, str(child_leaves))

        return root_item


    @pyqtSlot()
    def exploreTree(self):
        logger.debug("exploreTree started")
        selected_item = next(iter(self.decisionTreeList.selectedItems()), None)

        if not selected_item:
            logger.debug("No word selected for decision tree generation")
            return

        selected_index = self.decisionTreeList.indexFromItem(selected_item)
        # Check if an editor is open and retrieve its text
        profile = self.profile_manager.getCurrentProfile()
        word = selected_item.text()
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
        default_profile = self.profile_manager.getDefaultProfile()
        for name in sorted(self.profile_manager.getProfileNames()):
            self.profileComboBox.addItem(name, userData=name)
            if name == default_profile:
                index = self.profileComboBox.findData(name, Qt.ItemDataRole.UserRole)
                if index >= 0:
                    self.profileComboBox.setItemIcon(index, self.default_icon)
        if default_profile:
            index = self.profileComboBox.findData(default_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
        logger.debug("populateProfiles completed")
