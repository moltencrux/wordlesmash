from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import QDialog, QComboBox, QDialogButtonBox, QListWidgetItem, QItemDelegate, QTreeWidgetItem
from PyQt6.QtGui import QIcon
from .ui_loader import load_ui_class, UI_CLASSES
from .solver import DecisionTreeGuessManager
from .dialogs import ProgressDialog, BatchAddDialog
from .delegates import UpperCaseDelegate, MultiBadgeDelegate
from .profile_manager import Profile # , ProfileManager
from .wordle_game import Color
from .workers import DecisionTreeRoutesGetter
import logging


Ui_preferences = load_ui_class(*UI_CLASSES['MainPreferences'])

class MainPreferences(QDialog, Ui_preferences):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile_manager = parent.profile_manager
        self.word_length = 5
        self.guess_manager = None
        self.is_modified = False
        self.default_icon = QIcon.fromTheme("emblem-default", QIcon())  # Fallback to empty icon
        self.initUI()
        self.loadSettings()

    def initUI(self):
        self.setupUi(self)
        logging.debug(f"initUI: QComboBox item count before clear: {self.profileComboBox.count()}")
        self.profileComboBox.clear()
        logging.debug(f"initUI: QComboBox item count after clear: {self.profileComboBox.count()}")
        self.profileComboBox.setEditable(True)
        self.profileComboBox.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.addInitialPickButton.clicked.connect(self.addInitialPick)
        self.addPickButton.clicked.connect(self.addPick)
        self.addCandidateButton.clicked.connect(self.addCandidate)
        self.removeInitialPickButton.clicked.connect(self.removeInitialPick)
        self.removePickButton.clicked.connect(self.removePick)
        self.removeCandidateButton.clicked.connect(self.removeCandidate)
        self.addProfileButton.clicked.connect(self.addProfile)
        self.removeProfileButton.clicked.connect(self.removeProfile)
        self.setDefaultProfileButton.clicked.connect(self.setDefaultProfile)
        self.copyProfileButton.clicked.connect(self.copyProfile)
        self.removeTreeButton.clicked.connect(self.removeDecisionTree)
        self.exploreTreeButton.clicked.connect(self.exploreTree)
        self.manageCandidatesDialog = BatchAddDialog(self)
        self.managePicksDialog = BatchAddDialog(self)
        self.manageCandidatesButton.clicked.connect(self.manageCandidatesDialog.show)
        self.managePicksButton.clicked.connect(self.managePicksDialog.show)
        delegate_initial = UpperCaseDelegate(self.word_length, self.initialPicksList)
        delegate_initial.closeEditor.connect(self.onCloseInitPicksEditor)
        self.initialPicksList.setItemDelegate(delegate_initial)
        delegate_picks = UpperCaseDelegate(self.word_length, self.picksList)
        delegate_picks.closeEditor.connect(self.onClosePicksEditor)
        self.picksList.setItemDelegate(delegate_picks)
        delegate_candidates = UpperCaseDelegate(self.word_length, self.candidatesList)
        delegate_candidates.closeEditor.connect(self.onCloseCandidatesEditor)
        self.candidatesList.setItemDelegate(delegate_candidates)
        # Initialize chartTreeButton as disabled
        self.chartTreeButton.setEnabled(False)
        self.initialPicksList.itemSelectionChanged.connect(self.onInitialPicksListSelectionChanged)
        self.chartTreeButton.clicked.connect(self.onChartTreeButtonClicked)
        self.profileComboBox.activated.connect(self.onProfileChanged)
        self.buttonBox.accepted.connect(self.onOK)
        self.buttonBox.rejected.connect(self.onCancel)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.onApply)
        # Disable default button to prevent Enter key from accepting dialog
        self.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setAutoDefault(False)
        self.buttonBox.button(QDialogButtonBox.StandardButton.Apply).setAutoDefault(False)

        delegate = MultiBadgeDelegate(self.treeWidget, badge_size=32, radius=6, font_px=18, spacing=3, left_padding=0)
        self.treeWidget.setItemDelegateForColumn(0, delegate)
        self.treeWidget.setIndentation(35)

    def keyPressEvent(self, event):
        logging.debug(f"MainPreferences keyPressEvent: key={event.key()}, focusWidget={self.focusWidget()}")
        if event.key() == Qt.Key.Key_Escape:
            logging.debug("Esc key pressed in MainPreferences, triggering closeEvent")
            self.closeEvent(QCloseEvent())
            return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.profileComboBox.hasFocus() or self.profileComboBox.lineEdit().hasFocus():
                self.renameProfile()
                event.accept()  # Consume the Enter key event
                return
        super().keyPressEvent(event)

    def getCurrentModifiedProfile(self) -> Profile:
        """Get or create the current profile in modified, ensuring correct profile is updated."""
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            logging.debug("No profile selected for modification")
            raise ValueError("No profile selected")
        name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        if not name:
            logging.debug("No valid profile name for modification")
            raise ValueError("Invalid profile name")
        logging.debug(f"Getting modified profile for: {name}")
        return self.profile_manager.modifyProfile(name)

    def eventFilter(self, obj, event):
        if obj == self.profileComboBox.lineEdit() and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.renameProfile()
                return True  # Consume the Enter key event
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        logging.debug("MainPreferences closeEvent triggered")
        if self.is_modified or self.profile_manager.has_pending_changes():
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
        candidates_count = self.candidatesList.count()
        picks_count = self.picksList.count()
        self.candidatesCountLabel.setText(f"({candidates_count})")
        self.picksCountLabel.setText(f"({picks_count})")
        logging.debug(f"Updated labels: Candidates ({candidates_count}), Picks ({picks_count})")

    def getUniqueProfileName(self, base_name):
        """Generate a unique profile name by appending (N) if necessary."""
        profiles = [self.profileComboBox.itemData(i, Qt.ItemDataRole.UserRole) for i in range(self.profileComboBox.count())]
        if base_name not in profiles:
            return base_name
        i = 1
        while f"{base_name} ({i})" in profiles:
            i += 1
        return f"{base_name} ({i})"

    @pyqtSlot()
    def onInitialPicksListSelectionChanged(self):
        """Enable chartTreeButton if a word is selected in initialPicksList, disable otherwise."""
        has_selection = len(self.initialPicksList.selectedItems()) > 0
        self.chartTreeButton.setEnabled(has_selection)
        logging.debug(f"chartTreeButton enabled: {has_selection}")

    @pyqtSlot()
    def onChartTreeButtonClicked(self):
        """Generate a decision tree rule set for the selected word in initialPicksList."""
        selected_items = self.initialPicksList.selectedItems()
        if not selected_items:
            logging.debug("No word selected for decision tree generation")
            return
        # Check if an editor is open for the selected item
        selected_item = selected_items[0]
        selected_index = self.initialPicksList.indexFromItem(selected_item)
        # Check if an editor is open and retrieve its text
        editor_text = None
        if self.initialPicksList.isPersistentEditorOpen(selected_item):
            logging.debug("Editor open for selected item, retrieving text")
            editor = self.initialPicksList.itemWidget(selected_item)
            if isinstance(editor, QLineEdit):
                editor_text = editor.text().strip().upper()
                logging.debug(f"Editor text: {editor_text}")
        if editor_text:
            if len(editor_text) != self.word_length or not editor_text.isalpha():
                logging.debug(f"Invalid editor text: {editor_text}")
                QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
                self.initialPicksList.closePersistentEditor(selected_item)
                self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                self.addInitialPickButton.setEnabled(True)
                return
            legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count())}
            if editor_text not in legal_picks:
                reply = QMessageBox.question(
                    self, "Add to Picks?",
                    f"'{editor_text}' is not in the legal picks. Add it to picks.txt?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.picksList.addItem(editor_text)
                    profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
                    profile.picks.append(editor_text)
                    profile.dirty = True
                    self.updateCountLabels()
                else:
                    logging.debug(f"User declined to add {editor_text} to picks")
                    self.initialPicksList.closePersistentEditor(selected_item)
                    self.initialPicksList.takeItem(self.initialPicksList.row(selected_item))
                    self.addInitialPickButton.setEnabled(True)
                    return
            self.initialPicksList.closePersistentEditor(selected_item)
            self.addInitialPickButton.setEnabled(True)
        pick = selected_item.text().split(" (")[0].strip()
        if not pick:
            logging.debug("Empty word selected for decision tree generation")
            QMessageBox.warning(self, "Invalid Word", "The selected word is empty or invalid.")
            return
        profile_name = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
        logging.debug(f"Generating decision tree for word: {pick} in profile: {profile_name}")
        self.spawnDecisionTreeRoutesGetter(pick)

    @pyqtSlot(str, bool)
    def updateDecisionTrees(self, pick, success):
        """Update decisionTreeList and initialPicksList after DecisionTreeRoutesGetter finishes."""
        parent = self.parent()
        self.chartTreeButton.setEnabled(True)
        if success:
            parent.statusBar.showMessage(f"Decision tree generated for {pick}")
            # Add to decisionTreeList if not already present
            if pick not in [self.decisionTreeList.item(i).text() for i in range(self.decisionTreeList.count())]:
                self.decisionTreeList.addItem(pick)
            for i in range(self.initialPicksList.count()):
                if self.initialPicksList.item(i).text() == pick:
                    self.initialPicksList.takeItem(i)
                    break
            self.saveSettings()
        else:
            parent.statusBar.showMessage(f"Failed to generate decision tree for {pick}")
            QMessageBox.warning(self, "Error", f"Failed to generate decision tree for '{pick}'")

    @pyqtSlot()
    def removeDecisionTree(self):
        selected_items = self.decisionTreeList.selectedItems()
        if not selected_items:
            logging.debug("No decision tree selected for removal")
            QMessageBox.warning(self, "No Selection", "Please select a decision tree to remove.")
            return
        word = selected_items[0].text()
        profile_name = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.modifyProfile(profile_name, profile_name)
        dtree_dir = self.profile_manager.app_data_path / "profiles" / profile_name / "dtree"
        tree_file = dtree_dir / f"{word}.txt"
        if tree_file.exists():
            try:
                tree_file.unlink()
                logging.debug(f"Deleted decision tree file: {tree_file}")
                if word in profile.dt:
                    del profile.dt[word]
                    profile.dirty = True
            except OSError as e:
                logging.error(f"Failed to delete decision tree file {tree_file}: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete decision tree for '{word}'.")
                return
        # Remove from decisionTreeList
        self.decisionTreeList.takeItem(self.decisionTreeList.currentRow())
        if word not in [self.initialPicksList.item(i).text().split(" (")[0] for i in range(self.initialPicksList.count())]:
            self.initialPicksList.addItem(word)
            profile.initial_picks.append(word)
            profile.dirty = True
        self.is_modified = True
        self.guess_manager = None
        logging.debug("Invalidated guess_manager due to decision tree removal")
        self.parent().statusBar.showMessage(f"Removed decision tree for {word}")

    def loadSettings(self):
        self.profileComboBox.clear()
        default_profile = self.profile_manager.getDefaultProfile()
        profile_names = self.profile_manager.getProfileNames()
        for name in profile_names:
            self.profileComboBox.addItem(name, userData=name)
            index = self.profileComboBox.count() - 1
            if name == default_profile:
                self.profileComboBox.setItemIcon(index, self.default_icon)
            else:
                self.profileComboBox.setItemIcon(index, QIcon())
        current_profile = self.profile_manager.getCurrentProfile()
        if current_profile:
            index = self.profileComboBox.findData(current_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
            else:
                self.profileComboBox.setCurrentIndex(0)
                self.profile_manager.setCurrentProfile(profile_names[0] if profile_names else None)
        else:
            if profile_names:
                self.profileComboBox.setCurrentIndex(0)
                self.profile_manager.setCurrentProfile(profile_names[0])
        self.loadProfileSettings(self.profileComboBox.currentIndex())
        logging.debug(f"loadSettings completed, profileComboBox items: {self.profileComboBox.count()}")

    @pyqtSlot(int)
    def loadProfileSettings(self, index: int):
        if index < 0:
            return
        name = self.profileComboBox.itemData(index, Qt.ItemDataRole.UserRole)
        if not name:
            logging.debug(f"No valid profile name at index {index}")
            return
        logging.debug(f"Loading profile settings for: {name}")
        self.profile_manager.setCurrentProfile(name)  # Ensure current_profile is updated
        profile = self.profile_manager.loadProfile(name)
        self.word_length = profile.word_length
        self.initialPicksList.clear()
        for pick in profile.initial_picks:
            item = QListWidgetItem(pick)
            self.initialPicksList.addItem(item)
        self.picksList.clear()
        for pick in profile.picks:
            item = QListWidgetItem(pick)
            self.picksList.addItem(item)
        self.candidatesList.clear()
        for candidate in profile.candidates:
            item = QListWidgetItem(candidate)
            self.candidatesList.addItem(item)
        self.decisionTreeList.clear()
        for pick in profile.dt:
            self.decisionTreeList.addItem(pick)
        self.updateDelegates()
        self.updateCountLabels()
        self.picksList.repaint()
        self.candidatesList.repaint()
        logging.debug(f"Loaded profile settings: {name}, initial_picks: {profile.initial_picks}, picks: {profile.picks}, candidates: {profile.candidates}, word_length: {self.word_length}")
        logging.debug(f"ComboBox state: items={self.profileComboBox.count()}, currentIndex={self.profileComboBox.currentIndex()}, currentText={self.profileComboBox.currentText()}")

    @pyqtSlot(int)
    def onProfileChanged(self, index: int):
        """Handle profile switch via profileComboBox.activated signal."""
        self.loadProfileSettings(index)
        self.is_modified = True
        self.parent().resetGuessManager()
        logging.debug(f"Profile changed to index {index}, reset guess_manager and spawned suggestion getter")

    @pyqtSlot()
    def onApply(self):
        logging.debug("onApply called")
        self.profile_manager.commitChanges()
        self.is_modified = False
        self.parent().resetGuessManager()

    def updateDelegates(self):
        delegate_initial = UpperCaseDelegate(self.word_length, self.initialPicksList)
        delegate_initial.closeEditor.connect(self.onCloseInitPicksEditor)
        self.initialPicksList.setItemDelegate(delegate_initial)
        delegate_picks = UpperCaseDelegate(self.word_length, self.picksList)
        delegate_picks.closeEditor.connect(self.onClosePicksEditor)
        self.picksList.setItemDelegate(delegate_picks)
        delegate_candidates = UpperCaseDelegate(self.word_length, self.candidatesList)
        delegate_candidates.closeEditor.connect(self.onCloseCandidatesEditor)
        self.candidatesList.setItemDelegate(delegate_candidates)

    @pyqtSlot()
    def renameProfile(self):
        logging.debug("renameProfile called")
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            logging.debug("No profile selected for renaming")
            return
        old_name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        new_name = self.profileComboBox.lineEdit().text().strip()
        if not new_name or new_name == old_name:
            logging.debug(f"Invalid or unchanged new name: '{new_name}'")
            self.profileComboBox.lineEdit().setText(old_name)  # Restore old name
            return
        # Generate unique name if conflict
        new_name = self.getUniqueProfileName(new_name)
        logging.debug(f"Renaming profile from {old_name} to {new_name}")
        self.profileComboBox.blockSignals(True)
        try:
            if old_name in self.profile_manager.modified:
                profile = self.profile_manager.modified.pop(old_name)
            else:
                profile = self.profile_manager.loadProfile(old_name)
            profile.dirty = True
            profile.original_name = old_name
            self.profile_manager.modified[new_name] = profile
            self.profile_manager.setCurrentProfile(new_name)
            was_default = old_name == self.profile_manager.getDefaultProfile()
            if was_default:
                self.profile_manager.setDefaultProfile(new_name)
            self.profileComboBox.setItemText(current_index, new_name)
            self.profileComboBox.setItemData(current_index, new_name, Qt.ItemDataRole.UserRole)
            self.profileComboBox.setItemIcon(current_index, self.default_icon if was_default else QIcon())
            self.profileComboBox.lineEdit().setText(new_name)
            self.profileComboBox.clearEditText()
            self.loadProfileSettings(current_index)
        finally:
            self.profileComboBox.blockSignals(False)
        self.parent().statusBar.showMessage(f"Renamed profile from {old_name} to {new_name}")

    @pyqtSlot()
    def removeProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            return
        if self.profileComboBox.count() == 1:
            QMessageBox.warning(self, "Cannot Remove Profile", "Cannot remove the last profile.")
            return
        profile = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Remove Profile",
            f"Are you sure you want to remove the profile '{profile}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return
        logging.debug(f"Removing profile {profile}")
        self.profile_manager.deleteProfile(profile)
        self.profileComboBox.blockSignals(True)
        try:
            self.profileComboBox.removeItem(current_index)
            default_profile = self.profile_manager.getDefaultProfile()
            index = self.profileComboBox.findData(default_profile, Qt.ItemDataRole.UserRole)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
            else:
                self.profileComboBox.setCurrentIndex(0)
            new_profile = self.profileComboBox.itemData(self.profileComboBox.currentIndex(), Qt.ItemDataRole.UserRole)
            self.profile_manager.setCurrentProfile(new_profile)
            # Update icons for remaining profiles
            for i in range(self.profileComboBox.count()):
                name = self.profileComboBox.itemData(i, Qt.ItemDataRole.UserRole)
                self.profileComboBox.setItemIcon(i, self.default_icon if name == default_profile else QIcon())
        finally:
            self.profileComboBox.blockSignals(False)
        self.loadProfileSettings(self.profileComboBox.currentIndex())
        self.is_modified = True

    @pyqtSlot(QListWidgetItem)
    def validateInitialPick(self, item):
        text = item.text().split(" (")[0].strip().upper()
        if not text:
            self.initialPicksList.takeItem(self.initialPicksList.row(item))
            return
        profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.initialPicksList.takeItem(self.initialPicksList.row(item))
            return
        legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count())}
        if text not in legal_picks:
            reply = QMessageBox.question(
                self, "Add to Picks?",
                f"'{text}' is not in the legal picks. Add it to picks.txt?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.picksList.addItem(text)
                profile.picks.append(text)
                profile.dirty = True
                self.updateCountLabels()
            else:
                self.initialPicksList.takeItem(self.initialPicksList.row(item))
                return
        if text not in profile.initial_picks:
            profile.initial_picks.append(text)
            profile.dirty = True
        self.is_modified = True

    @pyqtSlot(QListWidgetItem)
    def validatePick(self, item):
        """Validate and normalize the pick."""
        text = item.text().strip().upper()
        if not text:
            self.picksList.takeItem(self.picksList.row(item))
            self.updateCountLabels()
            return
        profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.picksList.takeItem(self.picksList.row(item))
            self.updateCountLabels()
            return
        if text not in profile.picks:
            profile.picks.append(text)
            profile.dirty = True
        self.is_modified = True

    @pyqtSlot(QListWidgetItem)
    def validateCandidate(self, item):
        """Validate and normalize the candidate, adding to picksList if valid."""
        text = item.text().strip().upper()
        if not text:
            self.candidatesList.takeItem(self.candidatesList.row(item))
            self.updateCountLabels()
            return
        profile = self.profile_manager.modifyProfile(self.profile_manager.getCurrentProfile())
        item.setText(text)
        if len(text) != self.word_length or not text.isalpha():
            QMessageBox.warning(self, "Invalid Input", f"The word must be exactly {self.word_length} alphabetic characters long.")
            self.candidatesList.takeItem(self.candidatesList.row(item))
            self.updateCountLabels()
            return
        legal_picks = {self.picksList.item(i).text() for i in range(self.picksList.count())}
        if text not in legal_picks:
            self.picksList.addItem(text)
            profile.picks.append(text)
            profile.dirty = True
            self.updateCountLabels()
        if text not in profile.candidates:
            profile.candidates.append(text)
            profile.dirty = True
        self.is_modified = True

    @pyqtSlot()
    def removePick(self):
        profile = self.getCurrentModifiedProfile()
        current_item = self.picksList.currentItem()
        if current_item:
            text = current_item.text()
            if text in profile.picks:
                profile.picks.remove(text)
                profile.dirty = True
            self.picksList.takeItem(self.picksList.currentRow())
            self.is_modified = True
            logging.debug(f"Removed pick {text} from profile {self.profile_manager.getCurrentProfile()}")

    @pyqtSlot()
    def savePicksToFile(self):
        profile_name = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.modifyProfile(profile_name)
        profile.picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        profile.dirty = True
        self.is_modified = True

    @pyqtSlot()
    def addInitialPick(self):
        """Add a new item to initialPicksList and enter edit mode."""
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addInitialPickButton.setDisabled(True)
        profile = self.profile_manager.getCurrentProfile()
        self.initialPicksList.addItem(new_item)
        self.initialPicksList.scrollToBottom()
        self.initialPicksList.setCurrentItem(new_item)
        self.initialPicksList.setFocus()
        try:
            self.initialPicksList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for initialPicksList: {e}")
        self.is_modified = True

    @pyqtSlot()
    def onOK(self):
        logging.debug("onOK called")
        self.onApply()
        self.parent().resetGuessManager()
        self.parent().spawnSuggestionGetter()
        self.accept()

    @pyqtSlot()
    def onCancel(self):
        logging.debug("onCancel called")
        self.profile_manager.modified.clear()
        self.profile_manager.to_delete.clear()
        self.profile_manager._default_profile = self.profile_manager.settings.value("default_profile", defaultValue=None)
        self.is_modified = False
        self.reject()

    @pyqtSlot()
    def addPick(self):
        """Add a new item to picksList and enter edit mode."""
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addPickButton.setDisabled(True)
        profile = self.profile_manager.getCurrentProfile()
        self.picksList.addItem(new_item)
        self.picksList.scrollToBottom()
        self.picksList.setCurrentItem(new_item)
        self.picksList.setFocus()
        try:
            self.picksList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for picksList: {e}")
        self.updateCountLabels()
        self.is_modified = True

    @pyqtSlot()
    def addCandidate(self):
        new_item = QListWidgetItem("")
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable)
        self.addCandidateButton.setDisabled(True)
        profile = self.profile_manager.getCurrentProfile()
        self.candidatesList.addItem(new_item)
        self.candidatesList.scrollToBottom()
        self.candidatesList.setCurrentItem(new_item)
        self.candidatesList.setFocus()
        try:
            self.candidatesList.editItem(new_item)
        except Exception as e:
            logging.error(f"Failed to enter edit mode for candidatesList: {e}")
        self.updateCountLabels()
        self.is_modified = True

    @pyqtSlot()
    def removeInitialPick(self):
        profile = self.getCurrentModifiedProfile()
        current_item = self.initialPicksList.currentItem()
        if current_item:
            text = current_item.text()
            if text in profile.initial_picks:
                profile.initial_picks.remove(text)
                profile.dirty = True
            self.initialPicksList.takeItem(self.initialPicksList.currentRow())
            self.is_modified = True
            logging.debug(f"Removed initial pick {text} from profile {self.profile_manager.getCurrentProfile()}")

    @pyqtSlot()
    def setDefaultProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            return
        profile_name = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        if profile_name == self.profile_manager.getDefaultProfile():
            logging.debug(f"Profile {profile_name} is already default, skipping")
            return
        self.profile_manager.setDefaultProfile(profile_name)
        for i in range(self.profileComboBox.count()):
            name = self.profileComboBox.itemData(i, Qt.ItemDataRole.UserRole)
            self.profileComboBox.setItemIcon(i, self.default_icon if name == profile_name else QIcon())
        self.parent().statusBar.showMessage(f"Set {profile_name} as default profile")
        self.is_modified = True

    @pyqtSlot()
    def removeCandidate(self):
        profile = self.getCurrentModifiedProfile()
        current_item = self.candidatesList.currentItem()
        if current_item:
            text = current_item.text()
            if text in profile.candidates:
                profile.candidates.remove(text)
                profile.dirty = True
            self.candidatesList.takeItem(self.candidatesList.currentRow())
            self.is_modified = True
            logging.debug(f"Removed candidate {text} from profile {self.profile_manager.getCurrentProfile()}")

    @pyqtSlot()
    def addProfile(self):
        dialog = NewProfileDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.nameEdit.text().strip()
            name = self.getUniqueProfileName(name)
            length = dialog.lengthSpinBox.value()
            logging.debug(f"Adding new profile: {name}")
            profile = Profile(word_length=length, game_type=GameType.WORDLE, dirty=True)
            self.profile_manager.modified[name] = profile
            self.profile_manager.setCurrentProfile(name)
            self.profileComboBox.blockSignals(True)
            try:
                self.profileComboBox.addItem(name, userData=name)
                index = self.profileComboBox.count() - 1
                self.profileComboBox.setCurrentIndex(index)
                default_profile = self.profile_manager.getDefaultProfile()
                self.profileComboBox.setItemIcon(index, self.default_icon if name == default_profile else QIcon())
            finally:
                self.profileComboBox.blockSignals(False)
            self.loadProfileSettings(self.profileComboBox.currentIndex())
            self.is_modified = True

    @pyqtSlot()
    def copyProfile(self):
        current_index = self.profileComboBox.currentIndex()
        if current_index < 0:
            logging.debug("No profile selected to copy")
            QMessageBox.warning(self, "No Profile Selected", "Please select a profile to copy.")
            return
        source_profile = self.profileComboBox.itemData(current_index, Qt.ItemDataRole.UserRole)
        new_name = self.getUniqueProfileName(f"Copy of {source_profile}")
        logging.debug(f"Copying profile {source_profile} to {new_name}")
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
            logging.debug(f"Added copied profile {new_name} to QComboBox at index {index}")
        finally:
            self.profileComboBox.blockSignals(False)
        self.loadProfileSettings(self.profileComboBox.currentIndex())
        self.parent().statusBar.showMessage(f"Copied profile {source_profile} to {new_name}")
        self.is_modified = True

    @pyqtSlot()
    def saveSettings(self):
        profile_name = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.modifyProfile(profile_name)
        profile.picks = [self.picksList.item(i).text() for i in range(self.picksList.count())]
        profile.candidates = [self.candidatesList.item(i).text() for i in range(self.candidatesList.count())]
        profile.initial_picks = [
            self.initialPicksList.item(i).text().split(" (")[0]
            for i in range(self.initialPicksList.count())
        ]
        profile.word_length = self.word_length
        profile.dirty = True
        self.is_modified = True

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onCloseInitPicksEditor(self, editor, hint):
        self.onCloseEditor(editor, hint)
        self.addInitialPickButton.setEnabled(True)

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onClosePicksEditor(self, editor, hint):
        self.onCloseEditor(editor, hint)
        self.addPickButton.setEnabled(True)

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onCloseCandidatesEditor(self, editor, hint):
        self.onCloseEditor(editor, hint)
        self.addCandidateButton.setEnabled(True)

    @pyqtSlot("QWidget*", QItemDelegate.EndEditHint)
    def onCloseEditor(self, editor, hint):
        delegate = self.sender()
        list_widget = delegate.parent()
        if isinstance(delegate, UpperCaseDelegate) and delegate.current_index.isValid():
            index = delegate.current_index
            model = index.model()
            item_text = model.data(index)
            if index.isValid() and not item_text.strip():
                editor.clear()
                model.removeRow(index.row())
            self.updateCountLabels()

    def spawnDecisionTreeRoutesGetter(self, pick):
        """Start a DecisionTreeRoutesGetter thread to generate a decision tree for the given pick."""
        parent = self.parent()
        parent.statusBar.showMessage(f"Generating decision tree for {pick}...")

        # Create a thread that will launch a search
        self.chartTreeButton.setDisabled(True)
        if self.guess_manager is None:
            current_profile = self.profile_manager.getCurrentProfile()
            profile = self.profile_manager.loadProfile(current_profile)
            self.guess_manager = DecisionTreeGuessManager(
                profile.picks,
                profile.candidates,
                length=profile.word_length,
                cache_path=self.profile_manager.app_cache_path()
            )
            logging.debug(f"Created new DecisionTreeGuessManager for pick: {pick}")
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
                    stack.append((item,  new_dt))
                else:
                    item.setText(1, '1') # Leaves have value 1

        # Sum the number of leaf decendents under each item
        for item in reversed(end):
            child_leaves = sum(int(item.child(i).text(1)) for i in range(item.childCount()))
            item.setText(1, str(child_leaves))

        return root_item


    @pyqtSlot()
    def exploreTree(self):
        """Generate a decision tree rule set for the selected word in initialPicksList."""

        selected_item = next(iter(self.decisionTreeList.selectedItems()), None)

        if not selected_item:
            logging.debug("No word selected for decision tree generation")
            return

        selected_index = self.decisionTreeList.indexFromItem(selected_item)
        # Check if an editor is open and retrieve its text
        current_profile = self.profile_manager.getCurrentProfile()
        profile = self.profile_manager.loadProfile(current_profile)

        tree = {selected_item.text(): profile.dt[selected_item.text()]}


        tree_widget_item = self.create_tree_widget_items_it(tree)
        self.treeWidget.addTopLevelItem(tree_widget_item)
        tree_widget_item.setExpanded(True)
