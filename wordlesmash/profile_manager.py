from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set
from pathlib import Path
from PyQt6.QtCore import (QSettings, QStandardPaths, pyqtSignal, pyqtSlot,
    QObject, QModelIndex, QStringListModel
)
from .tree_utils import routes_to_dt, read_decision_routes, dt_to_text
from .models import PicksModel, StringSetModel
import logging
import shutil
from weakref import WeakKeyDictionary, WeakValueDictionary
from typing import List
import time

logger = logging.getLogger(__name__)

class GameType(Enum):
    WORDLE = "wordle"
    NYT_NORMAL = "NYT - Normal Mode"
    OTHER = "other"

@dataclass
class Profile:
    word_length: int = 5
    dt: Dict[str, Optional[dict]] = field(default_factory=dict)  # {pick: path to dtree/<pick>.txt}
    dt_model: StringSetModel = field(default_factory=StringSetModel)
    game_type: GameType = GameType.WORDLE
    candidates: Set[str] = field(default_factory=set)
    picks: Set[str] = field(default_factory=set)
    model: PicksModel = field(default_factory=PicksModel)
    initial_picks: StringSetModel = field(default_factory=StringSetModel)
    saved_name: Optional[str] = None
    writeback_words: bool = False
    writeback_settings: bool = False
    pending_dt_changes: Dict[str, set] = field(default_factory=lambda: {"added": set(), "deleted": set()})


class ProfileManager(QObject):

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings()
        self.app_data_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self._app_cache_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
        self._prev_profile = None
        self.reset()

    @pyqtSlot(QModelIndex, QModelIndex, 'QList<int>')
    def on_data_changed(self, topLeft: QModelIndex, bottomRight: QModelIndex, roles):
        logger.debug(f"on_data_changed: {topLeft}, {bottomRight}, {list(roles)}")
        sender = self.sender()
        name = self._profile_name_by_model.get(sender)
        if name:
            self.modifyProfileWords(name)

    def reset(self, parent=None, settings=None):

        self.modified: Dict[str, Profile] = {}
        self.loaded: Dict[str, Profile] = {}
        self.to_delete: Set[str] = set()  # Track profiles to delete on OK/Apply
        self._profile_names = set(self._getSavedProfileNames())
        self._profile_name_by_model = WeakKeyDictionary()

        if not self._profile_names:
            self.modified["Basic"] = Profile()

        self._default_profile = self.settings.value("default_profile",
            defaultValue=next(iter(self._profile_names), "Basic"))
        
        self.current_profile = self._prev_profile or self.getDefaultProfile()
        self._prev_profile = self.current_profile

    def discardChanges(self):
        """Discard all pending changes and reload profiles."""
        logger.debug("Discarding changes in ProfileManager")
        self.reset()

        self.current_profile = self._prev_profile or self.getDefaultProfile()
        logger.debug(f"Changes discarded, default profile: {self._default_profile}, current profile: {self.current_profile}")

    def getCurrentProfileName(self) -> str:
        return self.current_profile

    def getCurrentProfile(self) -> Profile:
        return self.loadProfile(self.getCurrentProfileName())

    def setCurrentProfile(self, name: str):
        self.current_profile = name
        logger.debug(f"Set current profile: {name}")

    def getDefaultProfile(self) -> Optional[str]:
        return self._default_profile

    def setDefaultProfile(self, name: str):
        self._default_profile = name


    def _getSavedProfileNames(self) -> List[str]:
        self.settings.beginGroup("profiles")
        names = self.settings.childGroups()
        self.settings.endGroup()
        return names

    def getProfileNames(self) -> List[str]:
        # XXX maybe just _profile_names if we keep it in sync right
        return self._profile_names | self.modified.keys()

    def getPicks(self) -> Set[str]:
        profile = self.loadProfile(self.current_profile)
        return profile.model.get_picks()

    def getCandidates(self) -> Set[str]:
        profile = self.loadProfile(self.current_profile)
        return profile.model.get_candidates()

    def getDecisionTrees(self) -> Dict[str, str]:
        profile = self.loadProfile(self.current_profile)
        return profile.dt

    def getWordLength(self) -> int:
        profile = self.loadProfile(self.current_profile)
        return profile.word_length

    def app_cache_path(self) -> str:
        return str(self._app_cache_path)

    @pyqtSlot(str)
    def changeGameType(self, game_type: str):
        profile = self.loadProfile(self.current_profile)
        profile.game_type = GameType(game_type)
        # profile.writeback_words = True
        profile.writeback_settings = True
        self.invalidate_all_dt(profile)

    def loadProfile(self, name: str) -> Profile:
        if name in self.modified:
            logger.debug(f"Loading modified profile: {name}")
            return self.modified[name]
        if name in self.loaded:
            return self.loaded[name]
        profile = Profile()
        # Tells us what name the Profile was saved under (if any), in case of later
        # deletion or renaming. Newly created profiles were never saved 
        self.settings.beginGroup("profiles")
        if name not in self.to_delete and name in self.settings.childGroups():
            profile.saved_name = name

        self.settings.endGroup()

        self.settings.beginGroup(f"profiles/{name}")
        profile.word_length = int(self.settings.value("word_length", 5))
        profile.game_type = GameType(self.settings.value("game_type", GameType.WORDLE.value))

        # Handle initial_picks as list
        for pick in self.settings.value("initial_picks", []) or []: # [] maybe for legacy profile
            profile.initial_picks.add_pick(pick)

        profile.dt = {}
        profile_dir = self.app_data_path / "profiles" / name

        start = time.time()
        # Load candidates from candidates.txt
        candidates_file = profile_dir / "candidates.txt"
        if candidates_file.exists():
            with candidates_file.open("r", encoding="utf-8") as f:
                candidates = sorted(line.strip().upper() for line in f if line.strip())  # Pre-sort
            profile.model.batch_add_candidates(candidates)
            logger.debug(f"Loaded {len(candidates)} candidates for profile '{name}'")

        # Load picks from picks.txt
        picks_file = profile_dir / "picks.txt"
        if picks_file.exists():
            with picks_file.open("r", encoding="utf-8") as f:
                picks = sorted(line.strip().upper() for line in f if line.strip())  # Pre-sort
            profile.model.batch_add_picks(picks)
            logger.debug(f"Loaded {len(picks)} picks for profile '{name}'")

        # Load decision trees
        if profile_dir.exists():
            dtree_dir = profile_dir / "dtree"
            if dtree_dir.exists():
                dt_files = dtree_dir.glob("*.txt")
                profile.dt = routes_to_dt(route for file in dt_files for route in
                    read_decision_routes(file)
                )
                for tree in profile.dt:
                    profile.dt_model.add_pick(tree)
        self.settings.endGroup()
        self.loaded[name] = profile
        self._profile_name_by_model[profile.model] = name
        # Connect signals with lambda to handle potential arg mismatches
        profile.model.dataChanged.connect(self.on_data_changed)
        profile.model.rowsInserted.connect(self.on_rows_changed)
        profile.model.rowsRemoved.connect(self.on_rows_changed)
        logger.debug(f"loadProfile: Loaded profile '{name}' in {time.time() - start:.2f} seconds")
        return profile

    @pyqtSlot(QModelIndex, int, int)
    def on_rows_changed(self, parent: QModelIndex, first: int, last: int):
        sender = self.sender()
        name = self._profile_name_by_model.get(sender)
        if name:
            self.modifyProfileWords(name)


    def saveProfile(self, name: str, profile: Profile):
        self.settings.beginGroup(f"profiles/{name}")
        self.settings.setValue("word_length", profile.word_length)
        self.settings.setValue("game_type", profile.game_type.value)
        self.settings.setValue("initial_picks", sorted(profile.initial_picks.get_picks()))
        self.settings.endGroup()
        self.settings.sync()


        profile_dir = self.app_data_path / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        # Save picks to picks.txt
        if profile.writeback_words or profile.saved_name != name:
            with open(profile_dir / "picks.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(profile.model.get_picks())))
            # Save candidates to candidates.txt
            with open(profile_dir / "candidates.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(profile.model.get_candidates())))
            logger.debug(f"Saved profile: {name}")
        dtree_dir = profile_dir / "dtree"
        dtree_dir.mkdir(parents=True, exist_ok=True)

        # Process pending decision tree changes

        for word in profile.pending_dt_changes["deleted"]:
            tree_file = dtree_dir / f"{word}.txt"
            if tree_file.exists():
                try:
                    tree_file.unlink()
                    logger.debug(f"Deleted decision tree file: {tree_file}")
                except Exception as e:
                    logger.error(f"Failed to delete decision tree file {tree_file}: {e}")

        if profile.saved_name == name:
            save_dts = profile.pending_dt_changes["added"]
        else:
            save_dts = profile.dt.keys()
        # the word 'bland' is not in profile.dt. why not?
        for word in save_dts:
            if word in profile.dt:
                with open(dtree_dir / f"{word}.txt", "w", encoding="utf-8") as f:
                    f.write(dt_to_text({word: profile.dt[word]}))

        profile.pending_dt_changes = {"added": set(), "deleted": set()}
        profile.writeback_words = False
        profile.writeback_settings = False

    def deleteProfile(self, name: str):
        # Mark profile for deletion instead of immediate removal

        profile = self.modified.pop(name, None) or self.loaded.pop(name, None)
        if profile:
            saved_name = profile.saved_name
        else:
            saved_name = name
        # Settings saved_name should be deleted if the profile has been renamed
        # since it was originally stored in settings
        if saved_name:
            self.to_delete.add(saved_name)
            logger.debug(f"Marked profile {saved_name} for deletion")

        self._profile_names.discard(name)
        if name == self.current_profile:
            self.current_profile = next(iter(self._profile_names), None)
            # XXX need to do more here
        if name == self._default_profile:
            self._default_profile = self.current_profile
            logger.debug(f"Deleted default profile {name}, _default_profile set to {self._default_profile}")

    def processDeletions(self):
        """Process all marked deletions, This removes the profile names marked
        for deletion from QSettings and associated profile paths."""
        for name in self.to_delete:
            logger.debug(f"Processing deletion for profile {name}")
            self.settings.beginGroup("profiles")
            self.settings.remove(name)
            self.settings.endGroup()
            profile_dir = self.app_data_path / "profiles" / name
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
                logger.debug(f"Deleted profile directory: {profile_dir}")
        self.to_delete.clear()
        logger.debug("All marked profiles deleted")

    def renameProfile(self, name: str, new_name: str) -> Profile:
        logger.debug(f"modifyProfile called for name: {name}, new_name: {new_name}")
        profile = self._modifyProfile(name)
        if new_name and new_name != name:
            self._profile_names.discard(name)
            if new_name != profile.saved_name:
                self.to_delete.add(profile.saved_name)
            else:
                self.to_delete.discard(profile.saved_name)
            if self.getDefaultProfile() == name:
                self.setDefaultProfile(new_name)
                logger.debug(f"Default profile renamed from {name} to {new_name}")

            profile.writeback_words = True
            profile.writeback_settings = True
    
        return profile

    @staticmethod
    def invalidate_all_dt(profile):
        for pick in profile.dt:
            profile.initial_picks.add_pick(pick)
        profile.pending_dt_changes['deleted'].update(profile.dt.keys())
        profile.dt.clear()
        profile.dt_model.clear()
        # how do we update the interface?

    def _modifyProfile(self, name: str) -> Profile:
        logger.debug(f"_modifyProfile called for name: {name}")
        profile = self.loadProfile(name)
        self.loaded.pop(name, None)
        self.modified[name] = profile
        # specific mod flags should be set by specific modfier methods
        return profile

    def modifyProfileWords(self, name: str) -> Profile:
        logger.debug(f"modifyProfile called for name: {name}, new_name: {name}")
        profile = self._modifyProfile(name)
        profile.writeback_words = True
        profile.writeback_settings = True
        self.invalidate_all_dt(profile)
        return profile
        # are we sure to need to invalidate dt?
        # do we ever use this when dts aren't invalidated? like...
        # when DTs are added?
        # when do we not need to invalidate?
            # 
    def modifyProfileSettings(self, name: str) -> Profile:
        profile = self._modifyProfile(name)
        profile.writeback_settings = True
        return profile


    def removeDecisionTree(self, word: str, profile_name: str =None):
        """Mark a decision tree for removal from a profile."""
        if not profile_name:
            profile_name = self.getCurrentProfileName()

        profile = self._modifyProfile(profile_name) # Q: modifyProfileSettings here? maybe not
        if word in profile.dt:
            profile.pending_dt_changes["deleted"].add(word)
            del profile.dt[word]
            profile.pending_dt_changes["added"].discard(word)
            profile.dt_model.remove_pick_by_text(word)
            logger.debug(f"Marked decision tree {word} for deletion in profile {profile_name}")

    # def addDecisionTree(self, name: str, tree_data: Dict[str, Optional[dict]]):
    def addDecisionTree(self, name: str, routes: List[Tuple[str]], success: bool):
        """Add or update a decision tree in a profile."""
        if success:

            tree_data = routes_to_dt(routes)
            profile = self.modifyProfileSettings(name)

            for word in tree_data.keys():
                profile.pending_dt_changes["added"].add(word)
                profile.dt_model.add_pick(word)
                profile.initial_picks.remove_pick_by_text(word)
            for word in profile.dt.keys() & tree_data.keys():
                profile.pending_dt_changes["deleted"].add(word)
                # even it's not deleted, it would just get overwritten I think
            profile.dt.update(tree_data)

    def has_pending_changes(self) -> bool:
        """Check if there are any pending changes to profiles or default profile."""
        current_default = self.settings.value("default_profile", defaultValue=None)
        default_changed = self._default_profile != current_default
        return bool(self.modified or self.to_delete or default_changed or
                    any(profile.pending_dt_changes["added"] or
                        profile.pending_dt_changes["deleted"]
                        for profile in self.modified.values()))

    def commitChanges(self):
        """Save all modified profiles, process deletions, and update default profile."""
        logger.debug("Committing changes in ProfileManager")
        self.processDeletions()  # Process pending deletions
        self._profile_names.update(self.modified.keys())
        for name, profile in self.modified.items():
            if profile.writeback_settings or profile.writeback_words:
                logger.debug(f"Saving profile: {name}")
                self.saveProfile(name, profile)
        # Save default profile if changed
        current_default = self.settings.value("default_profile", defaultValue=None)
        if self._default_profile != current_default:
            # Validate that _default_profile exists
            valid_profiles = set((*self.getProfileNames(), *self.modified.keys()))
            if self._default_profile is None or self._default_profile in valid_profiles:
                self.settings.setValue("default_profile", self._default_profile)
                self.settings.sync()
                logger.debug(f"Saved default profile to QSettings: {self._default_profile}")
            else:
                logger.warning(f"Invalid default profile {self._default_profile}, not saving to QSettings")
        self.modified.clear()
        logger.debug("All changes committed, cleared modified profiles")


    def addPick(self, text):
        profile_name = self.getCurrentProfileName()
        profile = self.modifyProfileWords(profile_name)
        return profile.model.add_pick(text)

    def addCandidate(self, text):
        profile_name = self.getCurrentProfileName()
        profile = self.modifyProfileWords(profile_name)
        return profile.model.add_candidate(text)

    def removePick(self, index):
        logger.debug("removePick started")

        if index.isValid():
            model = index.model()
            profile_name = self.getCurrentProfileName()
            profile = self.modifyProfileWords(profile_name)
            if hasattr(model, 'sourceModel'):
                pick_proxy, model = model, model.sourceModel()
                index, proxy_index = pick_proxy.mapToSource(index), index
            else:
                pick_proxy = None

            if model != profile.model:
                raise ValueError("model mismatch")

            text = model.data(index)
            model.remove_pick_by_text(text)
            if pick_proxy:
                pick_proxy.invalidate()

            self.removeInitialPick(text)
            self.removeDecisionTree(profile_name, text)

        logger.debug("removePick completed")

    def removeCandidate(self, index):
        logger.debug("removeCandidate started")

        if index.isValid():
            model = index.model()
            profile_name = self.getCurrentProfileName()
            profile = self.modifyProfileWords(profile_name)
            if hasattr(model, 'sourceModel'):
                candidates_proxy, model = model, model.sourceModel()
                index, proxy_index = candidates_proxy.mapToSource(index), index
            else:
                candidates_proxy = None

            if model != profile.model:
                raise ValueError("model mismatch")

            text = model.data(index)
            model.remove_candidate_by_text(text)
            if candidates_proxy:
                candidates_proxy.invalidate()

        logger.debug("removeCandidate completed")

    def removeInitialPick(self, target):
        logger.debug("removeInitialPick started")
        if isinstance(target, str):
            profile_name = self.getCurrentProfileName()
            profile = self.modifyProfileWords(profile_name)
            text = target
            model = profile.initial_picks
        elif isinstance(target, QModelIndex) and target.isValid():
            profile_name = self.getCurrentProfileName()
            profile = self.modifyProfileWords(profile_name)
            index = target
            model = index.model()
            text = model.data(index)
        else:
            raise ValueError('target must be a string or QAbstractModelIndex')
            return

        model.remove_pick_by_text(text)

    def batchAddPicks(self):
        ...

    def batchAddCandidates(self):
        ...

    def addInitialPick(self, text):
        profile_name = self.getCurrentProfileName()
        profile = self.modifyProfileSettings(profile_name)
        return profile.initial_picks.add_pick(text)



        