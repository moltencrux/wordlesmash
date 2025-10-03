from PyQt6.QtCore import (Qt, pyqtSlot, QModelIndex, QAbstractListModel,
    QSortFilterProxyModel, QVariant, QTimer, QSize
)

from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
    QItemDelegate, QListWidgetItem, QMessageBox, QTreeWidgetItem, QListView,
    QApplication
)
from PyQt6.QtGui import QValidator
import logging
from typing import List, Dict, Optional, Any
from sortedcontainers import SortedDict
import bisect  # For insertion points

logger = logging.getLogger(__name__)

class FilterProxy(QSortFilterProxyModel):
    "Filters a model against any number of containers"

    def __init__(self, *excludes, parent=None):
        super().__init__(parent)
        self.excludes = (*excludes,)

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.excludes or not self.sourceModel():
            logger.debug("FilterProxy.filterAcceptsRow: Accepting all, incomplete configuration")
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        word = self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole)
        logger.debug(f"FilterProxy.filterAcceptsRow: word={word}, accepted={word not in self.excludes}")
        return not any(word in seq for seq in self.excludes)

class ValidatedProxy(QSortFilterProxyModel):
    "Filters a model against a validator"

    def __init__(self, validator, parent=None):
        super().__init__(parent)
        self.validator = validator

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.validator or not self.sourceModel():
            logger.debug("ValidatedProxy.filterAcceptsRow: Accepting all, incomplete configuration")
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        word = self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole)
        state, _, _ = self.validator.validate(word, 0)
        accepted = state == QValidator.State.Acceptable
        logger.debug(f"ValidatedProxy.filterAcceptsRow: word={word}, accepted={accepted}")
        return accepted

class PicksProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        logger.debug("PicksProxy initialized")

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.sourceModel():
            logger.error("PicksProxy.filterAcceptsRow: No source model set")
            return False
        idx = self.sourceModel().index(source_row, 0, source_parent)
        if not idx.isValid():
            logger.error(f"PicksProxy.filterAcceptsRow: Invalid index for row={source_row}")
            return False
        is_pick = self.sourceModel().data(idx, Qt.ItemDataRole.UserRole) == 'pick'
        text = self.sourceModel().data(idx, Qt.ItemDataRole.DisplayRole) or ""
        is_empty = text == "" and source_row == self.sourceModel().rowCount() - 1
        logger.debug(f"PicksProxy.filterAcceptsRow: row={source_row}, is_pick={is_pick}, text='{text}', is_empty={is_empty}")
        return is_pick or is_empty

class PicksModel(QAbstractListModel):
    def __init__(self, picks: Optional[Dict[str, str]] = None):
        super().__init__()
        self._items = SortedDict(picks if picks is not None else {})  # word -> role ('pick' or 'candidate')
        self._new_item_type = None
        self._empty_row = None
        self._update_empty_row()
        logger.debug("PicksModel initialized")

    def _update_empty_row(self):
        """Update _empty_row to last index if blank exists."""
        if self._empty_row is not None:
            self._empty_row = len(self._items)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items) + (1 if self._empty_row is not None else 0)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.column() != 0:
            return QVariant()
        row = index.row()
        if row == self._empty_row:
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                return ''
            elif role == Qt.ItemDataRole.UserRole:
                return self._new_item_type
            else:
                return QVariant()
        if row >= len(self._items):
            return QVariant()
        word = self._items.keys()[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return word
        if role == Qt.ItemDataRole.UserRole:
            return self._items[word]
        return QVariant()


    def flags(self, index: QModelIndex):
        default_flags = super().flags(index)
        if not index.isValid():
            return default_flags
        # allow items to be selectable, enabled, and editable
        return default_flags | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != 0:
            return False
        row = index.row()
        value = str(value)
        if role == Qt.ItemDataRole.EditRole:
            row = index.row()
            if row == self._empty_row:
                if value == '':
                    return False
                # Insert new item at sorted position
                sorted_row = self._items.bisect_left(value)
                self.beginInsertRows(QModelIndex(), sorted_row, sorted_row)
                self._items[value] = self._new_item_type
                self._empty_row = None
                self._new_item_type = None
                self.endInsertRows()
                logger.debug(f"setData: Added new item '{value}' at sorted row {sorted_row}")
                return True
            old_word = self._items.keys()[row]
            if value == '':
                self.removeRows(row, 1)
                return True
            if old_word == value:
                return True
            if value in self._items:
                return False
            self.beginRemoveRows(QModelIndex(), row, row)
            role_value = self._items.pop(old_word, None)
            self.endRemoveRows()
            new_row = self._items.bisect_left(value)
            self.beginInsertRows(QModelIndex(), new_row, new_row)
            self._items[value] = role_value
            self.endInsertRows()
            logger.debug(f"setData: Changed '{old_word}' to '{value}' and moved from row {row} to {new_row}")
            return True
        elif role == Qt.ItemDataRole.UserRole:
            if value not in ('candidate', 'pick'):
                return False
            row = index.row()
            if row == self._empty_row:
                self._new_item_type = value
                return True
            word = self._items.keys()[row]
            current_role = self._items.get(word)
            if current_role == value:
                return False
            self._items[word] = value
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.UserRole])
            logger.debug(f"setData: Updated role of '{word}' to '{value}' at row {row}")
            return True
        return False
        # QApplication.processEvents() # double check if necessary

    def batch_add_picks(self, words: List[str], is_candidate: bool = False):
        """Add multiple picks or candidates in one operation."""
        valid_words = {word.upper() for word in words if word.strip()}
        if not valid_words:
            logger.debug("batch_add_picks: No valid words to add")
            return
        new_words = valid_words - self._items.keys()
        if not new_words:
            logger.debug("batch_add_picks: All words are duplicates")
            return
        role = 'candidate' if is_candidate else 'pick'
        row_start = self.rowCount()
        row_end = row_start + len(new_words) - 1
        self.beginInsertRows(QModelIndex(), row_start, row_end)
        for word in sorted(new_words):
            self._items[word] = role
        self.endInsertRows()
        logger.debug(f"batch_add_picks: Added {len(new_words)} {'candidates' if is_candidate else 'picks'} from row {row_start} to {row_end}")
        QApplication.processEvents()

    def batch_add_candidates(self, words: List[str]):
        """Mark existing picks as candidates and add new candidates in one operation."""
        valid_words = {word.upper() for word in words if word.strip()}
        if not valid_words:
            logger.debug("batch_add_candidates: No valid words to add")
            return
        existing = set(self._items.keys())
        new_words = valid_words - existing
        updated_rows = []
        find = self.make_batch_finder()
        for word in valid_words & existing:
            if self._items[word] != 'candidate':
                row = find(word)
                if row != -1:
                    self._items[word] = 'candidate'
                    updated_rows.append(row)
        if new_words:
            row_start = self.rowCount()
            row_end = row_start + len(new_words) - 1
            self.beginInsertRows(QModelIndex(), row_start, row_end)
            for word in sorted(new_words):
                self._items[word] = 'candidate'
            self.endInsertRows()
            logger.debug(f"batch_add_candidates: Added {len(new_words)} new candidates from row {row_start} to {row_end}")
        if updated_rows:
            updated_rows.sort()
            start_idx = self.index(updated_rows[0])
            end_idx = self.index(updated_rows[-1])
            self.dataChanged.emit(start_idx, end_idx, [Qt.ItemDataRole.UserRole])
            logger.debug(f"batch_add_candidates: Updated {len(updated_rows)} existing picks to candidates")
        QApplication.processEvents()

    def make_batch_finder(self):
        """Create a function to find row indices with caching, resetting cache per call."""
        cache = {}  # Fresh cache per finder instance
        def finder(target: str) -> int:
            if target in cache:
                return cache[target]
            for i in range(len(cache), len(self._items)):
                found = self._items.keys()[i]
                cache[found] = i
                if found == target:
                    return i
            return -1
        return finder

    def _row_of_text(self, text):
        if text != '':
            if text in self._items:
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

    def add_candidate(self, text='', proxy=None):
        """Add a single candidate, returning proxy index if proxy provided."""
        text = text.upper()
        if text not in self._items or (text == '' and self._empty_row is None):
            row = self._items.bisect_left(text) if text else len(self._items)
            self.beginInsertRows(QModelIndex(), row, row)
            if text == '':
                self._new_item_type = 'candidate'
                self._empty_row = row
            else:
                self._items[text] = 'candidate'
            self.endInsertRows()
            self._update_empty_row()
            logger.debug(f"PicksModel.add_candidate: Added '{text}' at row {row}")
        else:
            row = self._row_of_text(text)
            if text == '':
                orig_item_type = self._new_item_type
                self._new_item_type = 'candidate'
            else:
                orig_item_type = self._items[text]
                self._items[text] = 'candidate'
            if orig_item_type != 'candidate':
                model_index = self.index(row, 0)
                self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.UserRole])
            logger.debug(f"PicksModel.add_candidate: '{text}' already exists, updated to candidate")
        model_index = self.index(row, 0)
        QApplication.processEvents()
        return proxy.mapFromSource(model_index) if proxy else model_index

    def add_pick(self, text='', proxy=None):
        """Add a single pick, returning proxy index if proxy provided."""
        text = text.upper()
        if text not in self._items or (text == '' and self._empty_row is None):
            row = self._items.bisect_left(text) if text else len(self._items)
            self.beginInsertRows(QModelIndex(), row, row)
            if text == '':
                self._new_item_type = 'pick'
                self._empty_row = row
            else:
                self._items[text] = 'pick'
            self.endInsertRows()
            self._update_empty_row()
            logger.debug(f"PicksModel.add_pick: Added '{text}' at row {row}")
        else:
            row = self._row_of_text(text)
            logger.debug(f"PicksModel.add_pick: '{text}' already exists, skipping")
        model_index = self.index(row, 0)
        QApplication.processEvents()
        return proxy.mapFromSource(model_index) if proxy else model_index


    def remove_pick_by_row(self, row):
        # this can just be removeRow as long as it works properly

        if not (0 <= row < len(self._items)):
            logger.error(f"PicksModel.remove_pick_by_row: Invalid row {row}, items count={len(self._items)}")
            return False
        try:
            text = self._items.keys()[row]
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._items[text]
            self.endRemoveRows()
            logger.debug(f"PicksModel.remove_pick_by_row: Successfully removed row {row}")
            QApplication.processEvents()
            return True
        except Exception as e:
            logger.error(f"PicksModel.remove_pick_by_row: Exception while removing row {row}: {e}")
            return False

    def remove_candidate_by_row(self, row):
        if not (0 <= row < len(self._items)):
            logger.error(f"PicksModel.remove_pick_by_row: Invalid row {row}, items count={len(self._items)}")
            return False
        text = self._items.keys()[row]
        if self._items[text] == 'candidate':
            self._items[text] = 'pick'
            model_index = self.index(row, 0)
            self.dataChanged.emit(model_index, model_index, [Qt.ItemDataRole.UserRole])
            logger.debug(f"PicksModel.remove_candidate_by_text: Removed candidate '{text}'")
            QApplication.processEvents()
            return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if parent.isValid() or row < 0 or row + count > self.rowCount():
            return False
        self.beginRemoveRows(parent, row, row + count - 1)
        for i in range(row, row + count):
            if i == self._empty_row:
                self._new_item_type = None
                self._empty_row = None
            else:
                word = self._items.keys()[row]
                self._items.pop(word, None)
        self.endRemoveRows()
        QApplication.processEvents()
        return True

    def removeRow(self, row, parent=QModelIndex()):
        return self.removeRows(row, 1, parent)

    def remove_pick_by_text(self, text):
        if text in self._items and self._items[text] == 'pick':
            row = self._items.index(text)
            self.removeRows(row, 1)

    def remove_candidate_by_text(self, text):
        if text in self._items and self._items[text] == 'candidate':
            row = self._items.index(text)
            self.removeRows(row, 1)

    def get_picks(self):
        return [word for word in self._items.keys() if self._items[word] == 'pick']

    def get_candidates(self):
        return [word for word in self._items.keys() if self._items[word] == 'candidate']

    def remove_pick_by_text(self, text, proxy=None):
        """Remove a pick by text, handling proxy if provided."""
        text = text.upper()
        if text in self._items and self._items[text] == 'pick':
            row = self._items.index(text)
            self.removeRows(row, 1)
            model_index = self.index(row, 0)
            logger.debug(f"PicksModel.remove_pick_by_text: Removed '{text}' at row {row}")
            return proxy.mapFromSource(model_index) if proxy else model_index
        QApplication.processEvents()
        return QModelIndex()

    def remove_candidate_by_text(self, text, proxy=None):
        """Remove a candidate by text, handling proxy if provided."""
        text = text.upper()
        if text in self._items and self._items[text] == 'candidate':
            row = self._items.index(text)
            self.removeRows(row, 1)
            model_index = self.index(row, 0)
            logger.debug(f"PicksModel.remove_candidate_by_text: Removed '{text}' at row {row}")
            return proxy.mapFromSource(model_index) if proxy else model_index
        QApplication.processEvents()
        return QModelIndex()

class AlphabeticProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self._initial_sort = (0, Qt.SortOrder.AscendingOrder)
        self.setDynamicSortFilter(False)  # Disable automatic sorting for manual control
        self._sorted = False  # Track if model is sorted

    def setSourceModel(self, source_model):
        super().setSourceModel(source_model)
        if self._initial_sort is not None:
            column, order = self._initial_sort
            self.sort(column, order)
            self._sorted = True
            logger.debug("AlphabeticProxy: Initial sort completed")

    def invalidate(self):
        """Mark model as unsorted and trigger sort if needed."""
        self._sorted = False
        if self.sourceModel():
            self.sort(self.sortColumn(), self.sortOrder())
            self._sorted = True
            logger.debug("AlphabeticProxy: Invalidated and re-sorted")

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """Optimize string comparisons for sorting."""
        left_data = self.sourceModel().data(left, Qt.ItemDataRole.DisplayRole) or ""
        right_data = self.sourceModel().data(right, Qt.ItemDataRole.DisplayRole) or ""
        return left_data.lower() < right_data.lower()  # Case-insensitive sorting

    def forceSort(self):
        """Manually trigger sorting if not already sorted."""
        if not self._sorted and self.sourceModel():
            self.sort(self.sortColumn(), self.sortOrder())
            self._sorted = True
            logger.debug("AlphabeticProxy: Forced sort")

class CandidatesProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        logger.debug("CandidatesProxy initialized")

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


class StringSetModel(QAbstractListModel):
    def __init__(self, picks: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self._items = SortedDict({str(p).upper(): True for p in picks} if picks is not None else {})
        logger.debug(f"InitialPicksModel.__init__: Initialized with {len(self._items)} picks")

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.column() != 0 or index.row() >= len(self._items):
            return QVariant()
        word = self._items.iloc[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return word
        return QVariant()

    def flags(self, index: QModelIndex):
        default_flags = super().flags(index)
        if not index.isValid():
            return default_flags
        return default_flags | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.EditRole:
            return False
        value = str(value).upper()
        old_word = self._items.iloc[index.row()]
        if old_word == value:
            return True
        if value in self._items:
            logger.debug(f"InitialPicksModel.setData: Duplicate value '{value}' at row {index.row()}")
            return False
        self.beginRemoveRows(QModelIndex(), index.row(), index.row())
        self._items.pop(old_word)
        self.endRemoveRows()
        self.beginInsertRows(QModelIndex(), self._items.bisect_left(value), self._items.bisect_left(value))
        self._items[value] = True
        self.endInsertRows()
        logger.debug(f"InitialPicksModel.setData: Changed '{old_word}' to '{value}'")
        QApplication.processEvents()
        return True

    def add_pick(self, text: str):
        """Add a single pick, maintaining sort order."""
        text = text.upper()
        row = self._items.bisect_left(text)
        if text in self._items:
            logger.debug(f"InitialPicksModel.add_pick: Duplicate pick '{text}'")
            model_index = self.index(row, 0)
        else:
            model_index = QModelIndex()
            self.beginInsertRows(model_index, row, row)
            self._items[text] = True
            self.endInsertRows()
            logger.debug(f"InitialPicksModel.add_pick: Added '{text}' at row {row}")

        QApplication.processEvents()
        return model_index

    def remove_pick_by_text(self, text: str):
        """Remove a pick by its text."""
        text = text.upper()
        if text not in self._items:
            logger.debug(f"InitialPicksModel.remove_pick_by_text: Pick '{text}' not found")
            return False
        row = self._items.index(text)
        self.beginRemoveRows(QModelIndex(), row, row)
        self._items.pop(text)
        self.endRemoveRows()
        logger.debug(f"InitialPicksModel.remove_pick_by_text: Removed '{text}' at row {row}")
        QApplication.processEvents()
        return True
    
    def clear(self):
        for text in self._items:
            self.remove_pick_by_text(text)

    def get_picks(self):
        """Return all picks as a list."""
        return list(self._items.keys())

    def __contains__(self, item):
        return item in self._items

    # def removeRows(self, row, count, parent=QModelIndex()):
    #     if parent.isValid() or row < 0 or (row + count) > len(self._items):
    #         return False
    #     self.beginRemoveRows(parent, row, row + count - 1)
    #     for t in self._items[row:row + count]:
    #         if t == '':
    #             self._new_item_role = None
    #             self._empty_row = None
    #         else:
    #             self._roles.pop(t, None)
    #     del self._items[row:row + count]
    #     self.endRemoveRows()
    #     return True

    # def removeRow(self, row, parent=QModelIndex()):
    #     return self.removeRows(row, 1, parent)