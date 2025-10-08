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
            else:
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
        valid_words = {word for word in words if word.strip()}
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
        valid_words = {word for word in words if word.strip()}
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

    def remove_pick_by_row(self, row, proxy=None):
        # this can just be removeRow as long as it works properly

        if not (0 <= row < len(self._items)):
            logger.error(f"PicksModel.remove_pick_by_row: Invalid row {row}, items count={len(self._items)}")
            return False

        model_index = self.index(row, 0)
        text = self._items.keys()[row]

        self.beginRemoveRows(QModelIndex(), row, row)
        del self._items[text]
        self.endRemoveRows()
        logger.debug(f"PicksModel.remove_pick_by_row: Successfully removed row {row}")
        QApplication.processEvents()
        return True


    def remove_candidate_by_row(self, row, proxy=None):
        if not (0 <= row < len(self._items)):
            logger.error(f"PicksModel.remove_pick_by_row: Invalid row {row}, items count={len(self._items)}")
            return False
        text = self._items.keys()[row]
        if self._items[text] == 'candidate':
            model_index = self.index(row, 0)
            self.setData(model_index, 'pick', Qt.ItemDataRole.UserRole)
            logger.debug(f"PicksModel.remove_candidate_by_text: Removed candidate '{text}'")
            # QApplication.processEvents()
            return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if parent.isValid() or row < 0 or row + count > self.rowCount():
            return False

        self.beginRemoveRows(parent, row, row + count - 1)
        if row + count >= len(self._items):
            self._empty_row = None
            self._new_item_type = None
        view = self._items.keys()
        del view[row:row + count]
        self.endRemoveRows()
        QApplication.processEvents()
        return True

    # Probably not necessary to overload as I believe the default implementation
    # just calls removeRows()
    # def removeRow(self, row, parent=QModelIndex()):
    #     return self.removeRows(row, 1, parent)

    def get_picks(self):
        return [word for word in self._items.keys() if self._items[word] in ('pick', 'candidate')]

    def get_candidates(self):
        return [word for word in self._items.keys() if self._items[word] == 'candidate']

    def remove_pick_by_text(self, text, proxy=None):
        """Remove a pick by text, handling proxy if provided."""
        if text in self._items and self._items[text] in ('candidate', 'pick'):
            row = self._items.index(text)
            return self.remove_pick_by_row(row, proxy)
        # QApplication.processEvents()
        return False

    def remove_candidate_by_text(self, text, proxy=None):
        """Remove a candidate by text, handling proxy if provided."""
        if text in self._items and self._items[text] == 'candidate':
            row = self._items.index(text)
            return self.remove_candidate_by_row(row, proxy=proxy)

        return False


    def __contains__(self, item):
        return item in self._items

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
        is_candidate = self.sourceModel().data(idx, Qt.ItemDataRole.UserRole) == 'candidate'
        if logger.isEnabledFor(logging.DEBUG):
            text = self.sourceModel().data(idx, Qt.ItemDataRole.DisplayRole) or ""
            logger.debug(f"CandidatesProxy.filterAcceptsRow: row={source_row}, is_candidate={is_candidate}, text='{text}'")
        return bool(is_candidate)


class StringSetModel(QAbstractListModel):
    def __init__(self, picks: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self._items = SortedDict({str(p): True for p in picks} if picks is not None else {})
        self._modified = False
        logger.debug(f"InitialPicksModel.__init__: Initialized with {len(self._items)} picks")

    def isModified(self):
        return self._modified

    def resetModified(self):
        self._modified = False

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
        value = str(value)
        old_word = self._items.iloc[index.row()]
        if old_word == value:
            return True
        if value in self._items:
            logger.debug(f"InitialPicksModel.setData: Duplicate value '{value}' at row {index.row()}")
            return False
        self._modified = True
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
        row = self._items.bisect_left(text)
        if text in self._items:
            logger.debug(f"InitialPicksModel.add_pick: Duplicate pick '{text}'")
            model_index = self.index(row, 0)
        else:
            self._modified = True
            model_index = QModelIndex()
            self.beginInsertRows(model_index, row, row)
            self._items[text] = True
            self.endInsertRows()
            logger.debug(f"InitialPicksModel.add_pick: Added '{text}' at row {row}")

        QApplication.processEvents()
        return model_index

    def remove_pick_by_text(self, text: str):
        """Remove a pick by its text."""
        if text not in self._items:
            logger.debug(f"InitialPicksModel.remove_pick_by_text: Pick '{text}' not found")
            return False
        self._modified = True
        row = self._items.index(text)
        self.beginRemoveRows(QModelIndex(), row, row)
        self._items.pop(text)
        self.endRemoveRows()
        logger.debug(f"InitialPicksModel.remove_pick_by_text: Removed '{text}' at row {row}")
        QApplication.processEvents()
        return True
    
    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_picks(self):
        """Return all picks as a list."""
        return list(self._items.keys())

    def __contains__(self, item):
        return item in self._items

    def removeRows(self, row, count, parent=QModelIndex()):
        if parent.isValid() or row < 0 or row + count > self.rowCount():
            return False

        self.beginRemoveRows(parent, row, row + count - 1)
        view = self._items.keys()
        del view[row:row + count]
        self.endRemoveRows()
        QApplication.processEvents()
        return True

    # Probably not necessary to overload as I believe the default implementation
    # just calls removeRows()
    # def removeRow(self, row, parent=QModelIndex()):
    #     return self.removeRows(row, 1, parent)