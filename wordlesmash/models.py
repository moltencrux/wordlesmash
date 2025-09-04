from PyQt6.QtCore import (Qt, pyqtSlot, QModelIndex, QAbstractListModel,
    QSortFilterProxyModel, QVariant, QTimer, QSize
)

from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
    QItemDelegate, QListWidgetItem, QMessageBox, QTreeWidgetItem, QListView
)
import logging

logger = logging.getLogger(__name__)

class PicksModel(QAbstractListModel):
    def __init__(self, picks={}):
        super().__init__()
        if not isinstance(picks, dict):
            raise ValueError('Picks must be of type dict')
        self._picks = picks # a dictionary keyed by picks/canididates, keyed by words and 'pick' or 'candidate' values
        self._items = list(picks.keys())
        self._new_item_type = None
        self._empty_row = None
        logger.debug(f"PicksModel initialized with {len(self._items)} items")

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            logger.debug(f"PicksModel.data: Invalid index {index.row()}")
            return QVariant()
        text = self._items[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            logger.debug(f"PicksModel.data: Display/EditRole, index={index.row()}, text='{text}'")
            return text
        if role == Qt.ItemDataRole.UserRole:
            return self._get_user_role_data(text) or QVariant()
        if role == Qt.ItemDataRole.SizeHintRole:
            logger.debug(f"PicksModel.data: SizeHintRole, index={index.row()}")
            return QSize(100, 30)  # Size for list item and editor
        return QVariant()


    def flags(self, index: QModelIndex):
        default_flags = super().flags(index)
        if not index.isValid():
            return default_flags
        # allow items to be selectable, enabled, and editable
        return default_flags | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            logger.debug(f"PicksModel.setData: Invalid index {index.row()}")
            return False

        text = str(value)
        if role == Qt.ItemDataRole.EditRole:
            orig_text = self._items[index.row()]

            logger.debug(f"PicksModel.setData: Processing text '{text}' at index {index.row()}")

            orig_role_data = self._get_user_role_data(orig_text)

            if text != orig_text:

                # Ensure candidate promotion preserved

                if text in self._picks:  # Merger
                    row = self._index_of_text(orig_text)  # only need if merger i think, o/w index.row
                    if orig_role_data == 'candidate':
                        self._picks[text] = orig_role_data
                    # Merger
                    self.beginRemoveRows(QModelIndex(), index.row(), index.row())
                    del self._items[index.row()]
                    self._picks.pop(orig_text, None)
                    self.endRemoveRows()
                    # check old type
                    # if merger, did types change?
                    if orig_role_data == 'candidate' and self._get_user_role_data(text) != 'candidate':
                        self._picks[text] = 'candidate'
                        self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [Qt.ItemDataRole.UserRole])

                else:
                    self._items[index.row()] = text
                    self._picks[text] = orig_role_data
                    self._picks.pop(orig_text, None)
                    # self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole])
                    self.dataChanged.emit(index, index, [Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole])

                if orig_text == '':
                    self._empty_row = None
                    self._new_item_type = None

                return True

        elif role == Qt.ItemDataRole.UserRole:
            if value in ('candidate', 'pick') and text in self._picks:
                self._picks[text] = value
                return True

        return False

    def _index_of_text(self, text):
        if text != '':
            if text in self._picks:
                return self._items.index(text)
        elif self._empty_row is not None:
            return self._empty_row
        return -1

    def _get_user_role_data(self, text):
        if text == '':
            return self._new_item_type
        elif text in self._picks:
            return self._picks[text]
        else:
            return None

    def add_candidate(self, text=''):

        new_index = self.rowCount()

        if text not in self._picks or (text == '' and self._empty_row is None):
            self.beginInsertRows(QModelIndex(), new_index, new_index)
            self._items.append(text)
            if text == '':
                self._new_item_type = 'candidate'
                self._empty_row = new_index
            else:
                self._picks[text] = 'candidate'
            self.endInsertRows()
            logger.debug(f"PicksModel.add_pick: Added '{text}'")
        else: # is it already a candidate? if so, do nothing, o/w dataChanged
            new_index = self._index_of_text(text) 
            if text == '':
                orig_item_type = self._new_item_type
                self._new_item_type = 'candidate'
            else:
                orig_item_type = self._picks[text]
                self._picks[text] = 'candidate'
            if orig_item_type != 'candidate':
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.UserRole])
            logger.debug(f"PicksModel.add_pick: '{text}' already exists, skipping")

        return  self.index(new_index)

    def add_pick(self, text=''):

        new_index = self.rowCount()

        if text not in self._picks or (text == '' and self._empty_row is None):
            self.beginInsertRows(QModelIndex(), new_index, new_index)
            self._items.append(text)
            if text == '':
                self._new_item_type = 'pick'
                self._empty_row = new_index
            else:
                self._picks[text] = 'pick'
            self.endInsertRows()
            logger.debug(f"PicksModel.add_pick: Added '{text}'")
            self.rowsInserted.emit(self.index(new_index), new_index, 0)
        else:
            new_index = self._index_of_text(text)
            logger.debug(f"PicksModel.add_pick: '{text}' already exists, skipping")

        return  self.index(new_index, 0)


    def remove_pick_by_row(self, row):

        if not (0 <= row < len(self._items)):
            logger.error(f"PicksModel.remove_pick_by_row: Invalid row {row}, items count={len(self._items)}")
            return False
        try:
            text = self._items[row]
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._items[row]
            del self._picks[text]
            self.endRemoveRows()
            logger.debug(f"PicksModel.remove_pick_by_row: Successfully removed row {row}")
            return True
        except Exception as e:
            logger.error(f"PicksModel.remove_pick_by_row: Exception while removing row {row}: {e}")
            return False

    def remove_candidate_by_row(self, row):
        if index != -1:
            text = self._items[row]
            if text in self._picks[text] == 'candidate':
                model_index = self.index(index, 0)
                self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.UserRole])
                logger.debug(f"PicksModel.remove_candidate_by_text: Removed candidate '{text}'")
                return True
        return False

    def remove_pick_by_text(self, text):
        idx = self._index_of_text(text)
        if idx != -1:
            return self.remove_pick_by_row(idx)
        return False

    def remove_candidate_by_text(self, text):
        idx = self._index_of_text(text)
        if idx != -1:
            return self.remove_candidate_by_row(idx)
        return False

    def get_picks(self):
        picks = set(self._picks.keys())
        logger.debug(f"PicksModel.get_picks: {picks}")
        return picks

    def get_candidates(self):
        candidates = {word for word, role in self._picks.items() if role == 'candidate'}
        logger.debug(f"PicksModel.get_candidates: {candidates}")
        return candidates

class AlphabeticProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self._initial_sort = (0, Qt.SortOrder.AscendingOrder)

    def setSourceModel(self, source_model):
        super().setSourceModel(source_model)
        if self._initial_sort is not None:
            column, order = self._initial_sort
            self.sort(column, order)

class CandidatesProxy(AlphabeticProxy):
    def __init__(self):
        super().__init__()
        logger.debug("CandidatesProxy initialized")
        self.setDynamicSortFilter(True)

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.sourceModel():
            logger.error("CandidatesProxy.filterAcceptsRow: No source model set")
            return False
        idx = self.sourceModel().index(source_row, 0, source_parent)
        if not idx.isValid():
            logger.error(f"CandidatesProxy.filterAcceptsRow: Invalid index for row={source_row}")
            return False
        is_cand = self.sourceModel().data(idx, Qt.ItemDataRole.UserRole) == 'candidate'
        text = self.sourceModel().data(idx, Qt.ItemDataRole.DisplayRole) or ""
        logger.debug(f"CandidatesProxy.filterAcceptsRow: row={source_row}, is_candidate={is_cand}, text='{text}'")
        return bool(is_cand)

