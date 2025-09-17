from PyQt6.QtCore import (Qt, pyqtSlot, QModelIndex, QAbstractListModel,
    QSortFilterProxyModel, QVariant, QTimer, QSize
)

from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
    QItemDelegate, QListWidgetItem, QMessageBox, QTreeWidgetItem, QListView
)
import logging

logger = logging.getLogger(__name__)

class PicksModel(QAbstractListModel):
    def __init__(self, picks=None):
        super().__init__()
        if not isinstance(picks, (dict, type(None))):
            raise ValueError('Picks must be of type dict or None')
        self._picks = picks if picks is not None else {} # a dictionary keyed by picks/canididates, keyed by words and 'pick' or 'candidate' values
        self._items = list(self._picks.keys())
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
                    row = self._row_of_text(orig_text)  # only need if merger i think, o/w index.row
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

    def _row_of_text(self, text):
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

        row = self.rowCount()

        if text not in self._picks or (text == '' and self._empty_row is None):
            self.beginInsertRows(QModelIndex(), row, row)
            self._items.append(text)
            if text == '':
                self._new_item_type = 'candidate'
                self._empty_row = row
            else:
                self._picks[text] = 'candidate'
            self.endInsertRows()
            logger.debug(f"PicksModel.add_pick: Added '{text}'")
        else: # is it already a candidate? if so, do nothing, o/w dataChanged
            row = self._row_of_text(text) 
            if text == '':
                orig_item_type = self._new_item_type
                self._new_item_type = 'candidate'
            else:
                orig_item_type = self._picks[text]
                self._picks[text] = 'candidate'
            if orig_item_type != 'candidate':
                self.dataChanged.emit(self.index(row), self.index(row), [Qt.ItemDataRole.UserRole])
            logger.debug(f"PicksModel.add_pick: '{text}' already exists, skipping")

        return  self.index(row)

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
            new_index = self._row_of_text(text)
            logger.debug(f"PicksModel.add_pick: '{text}' already exists, skipping")

        return  self.index(new_index, 0)


    def remove_pick_by_row(self, row):
        # this can just be removeRow as long as it works properly

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
        if not (0 <= row < len(self._items)):
            logger.error(f"PicksModel.remove_pick_by_row: Invalid row {row}, items count={len(self._items)}")
            return False
        text = self._items[row]
        if self._picks[text] == 'candidate':
            self._picks[text] = 'pick'
            model_index = self.index(row, 0)
            self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.UserRole])
            logger.debug(f"PicksModel.remove_candidate_by_text: Removed candidate '{text}'")
            return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if parent.isValid() or row < 0 or row + count > len(self._items):
            return False

        self.beginRemoveRows(parent, row, row + count - 1)
        for text in self._items[row:row+count]:
            if text != '':
                del self._picks[text]
        del self._items[row:row+count]
        self.endRemoveRows()
        return True

    def removeRow(self, row, parent=QModelIndex()):
        return self.removeRows(row, 1, parent)


    def remove_pick_by_text(self, text):
        idx = self._row_of_text(text)
        if idx != -1:
            return self.remove_pick_by_row(idx)
        return False

    def remove_candidate_by_text(self, text):
        idx = self._row_of_text(text)
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


class DisjointSetModel(QAbstractListModel):
    """
    Maintains two disjoint sets of items: 'left' and 'right'.
    Each item appears at most once and has a role 'left' or 'right'.
    An empty-string row may be used as a new-item editor; its role is stored in _new_item_role.
    """

    def __init__(self, items=None):
        super().__init__()
        if items is None:
            items = {}
        if not isinstance(items, dict):
            raise ValueError("items must be a dict mapping text -> role ('left'|'right')")
        # normalize roles and drop invalid roles
        normalized = {}
        for k, v in items.items():
            if v in ("left", "right"):
                normalized[k] = v
        self._items = list(normalized.keys())
        self._roles = normalized  # dict: text -> 'left'|'right'
        self._new_item_role = None  # role for empty new row (if present)
        self._empty_row = None  # index of empty-row if present
        # logger.debug(...)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return QVariant()
        text = self._items[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return text
        if role == Qt.ItemDataRole.UserRole:
            return self._get_role_for_text(text) or QVariant()
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(100, 30)
        return QVariant()

    def flags(self, index: QModelIndex):
        default_flags = super().flags(index)
        if not index.isValid():
            return default_flags
        return default_flags | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return False

        text_at_row = self._items[index.row()]

        if role == Qt.ItemDataRole.EditRole:
            new_text = str(value)
            old_text = text_at_row
            old_role = self._get_role_for_text(old_text)

            if new_text == old_text:
                return False

            # If new_text already exists in model, we must merge: remove this row
            # but preserve role if this row had one that should carry over.
            if new_text in self._roles:
                # If this row was an empty row, clear empty-row tracking
                if old_text == '':
                    self._empty_row = None
                    self._new_item_role = None

                # If the current row had a role and target already has the other role,
                # ensure resulting role is the one we want (here we keep existing target role).
                # Remove this row (merging into existing entry)
                self.beginRemoveRows(QModelIndex(), index.row(), index.row())
                del self._items[index.row()]
                # remove old text role if present and not same as new_text (old_text != new_text)
                self._roles.pop(old_text, None)
                self.endRemoveRows()
                # no explicit dataChanged for target; caller can query get_left/get_right
                return True
            else:
                # new_text is not present -> rename entry
                # preserve role mapping if present (including empty-row)
                role_value = old_role
                # Remove old mapping and place new mapping
                if old_text != '':
                    # normal text -> rename
                    del self._roles[old_text]
                else:
                    # clearing empty-row tracking
                    self._empty_row = None
                    self._new_item_role = None

                self._items[index.row()] = new_text
                if role_value in ("left", "right"):
                    # ensure disjointness: remove new_text from opposite role if somehow present (shouldn't)
                    self._roles.pop(new_text, None)
                    self._roles[new_text] = role_value
                # notify display/edit change
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole])
                return True

        elif role == Qt.ItemDataRole.UserRole:
            # Set explicit role for item at row (value must be 'left' or 'right')
            if value not in ("left", "right"):
                return False
            text = text_at_row
            if text == '':
                # set role for empty new row
                self._new_item_role = value
                return True
            # When assigning role to text, ensure disjointness:
            current = self._roles.get(text)
            if current == value:
                return False
            # assign new role (overwrites any prior role)
            self._roles[text] = value
            # emit change for this index
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.UserRole])
            return True

        return False

    def _row_of_text(self, text):
        if text != '':
            if text in self._roles:
                try:
                    return self._items.index(text)
                except ValueError:
                    return -1
        else:
            if self._empty_row is not None:
                return self._empty_row
        return -1

    def _get_role_for_text(self, text):
        if text == '':
            return self._new_item_role
        return self._roles.get(text)

    def _ensure_disjoint_and_set_role(self, text, role):
        """
        Ensure 'text' is not present with opposite role. If present with opposite role, change it to 'role'.
        If present already with same role, do nothing.
        """
        current = self._roles.get(text)
        if current == role:
            return
        # just set to desired role (since each text only maps to one role)
        self._roles[text] = role

    def add_left(self, text=''):
        return self._add_item_with_role(text, 'left')

    def add_right(self, text=''):
        return self._add_item_with_role(text, 'right')

    def _add_item_with_role(self, text, role):
        if role not in ("left", "right"):
            raise ValueError("role must be 'left' or 'right'")
        # if text exists and has same role, return its index
        idx = self._row_of_text(text)
        if idx != -1:
            # existing item: ensure role and emit if changed
            if text == '':
                orig = self._new_item_role
                self._new_item_role = role
                if orig != role and idx is not None:
                    model_index = self.index(idx, 0)
                    self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.UserRole])
            else:
                orig = self._roles.get(text)
                self._ensure_disjoint_and_set_role(text, role)
                if orig != role:
                    model_index = self.index(idx, 0)
                    self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.UserRole])
            return self.index(idx, 0)

        # insert new row
        new_index = self.rowCount()
        self.beginInsertRows(QModelIndex(), new_index, new_index)
        self._items.append(text)
        if text == '':
            self._new_item_role = role
            self._empty_row = new_index
        else:
            # ensure disjointness by removing any previous mapping (not expected)
            self._roles.pop(text, None)
            self._roles[text] = role
        self.endInsertRows()
        return self.index(new_index, 0)

    def remove_by_row(self, row):
        if not (0 <= row < len(self._items)):
            return False
        text = self._items[row]
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._items[row]
        if text == '':
            self._new_item_role = None
            self._empty_row = None
        else:
            self._roles.pop(text, None)
        self.endRemoveRows()
        return True

    def remove_by_text(self, text):
        idx = self._row_of_text(text)
        if idx != -1:
            return self.remove_by_row(idx)
        return False

    def removeRows(self, row, count, parent=QModelIndex()):
        if parent.isValid() or row < 0 or (row + count) > len(self._items):
            return False
        self.beginRemoveRows(parent, row, row + count - 1)
        for t in self._items[row:row + count]:
            if t == '':
                self._new_item_role = None
                self._empty_row = None
            else:
                self._roles.pop(t, None)
        del self._items[row:row + count]
        self.endRemoveRows()
        return True

    def removeRow(self, row, parent=QModelIndex()):
        return self.removeRows(row, 1, parent)

    def get_left(self):
        return {k for k, v in self._roles.items() if v == 'left'}

    def get_right(self):
        return {k for k, v in self._roles.items() if v == 'right'}
