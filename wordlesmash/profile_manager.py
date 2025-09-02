from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from pathlib import Path
from PyQt6.QtCore import QSettings, QStandardPaths
from .tree_utils import routes_to_dt, read_decision_routes, dt_to_text
import logging
import shutil
from collections import ChainMap

class GameType(Enum):
    WORDLE = "wordle"
    NYT_NORMAL = "NYT - Normal Mode"
    OTHER = "other"

@dataclass
class Profile:
    word_length: int = 5
    dt: Dict[str, Optional[dict]] = field(default_factory=dict)  # {pick: path to dtree/<pick>.txt}
    game_type: GameType = GameType.WORDLE
    candidates: Set[str] = field(default_factory=set)
    picks: Set[str] = field(default_factory=set)
    initial_picks: Set[str] = field(default_factory=set)  # {pick: status}
    saved_name: Optional[str] = None
    dirty: bool = False
    words_modified: bool = False
    pending_dt_changes: Dict[str, set] = field(default_factory=lambda: {"added": set(), "deleted": set()})

class ProfileManager:
    def __init__(self, parent=None, settings=None):
        self.settings = settings if settings is not None else QSettings()
        self.app_data_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self._app_cache_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
        self._prev_profile = None
        self.reset()

    def reset(self, parent=None, settings=None):

        self.modified: Dict[str, Profile] = {}
        self.loaded: Dict[str, Profile] = {}
        self.to_delete: List[str] = []  # Track profiles to delete on OK/Apply
        self._profile_names = set(self._getSavedProfileNames())

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

    def getCurrentProfile(self) -> Optional[str]:
        return self.current_profile

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

    def getPicks(self) -> List[str]:
        profile = self.loadProfile(self.current_profile)
        return sorted(profile.picks)

    def getCandidates(self) -> List[str]:
        profile = self.loadProfile(self.current_profile)
        return sorted(profile.candidates)

    def getDecisionTrees(self) -> Dict[str, str]:
        profile = self.loadProfile(self.current_profile)
        return profile.dt

    def getWordLength(self) -> int:
        profile = self.loadProfile(self.current_profile)
        return profile.word_length

    def app_cache_path(self) -> str:
        return str(self._app_cache_path)

    def loadProfile(self, name: str) -> Profile:
        if name in self.modified:
            logger.debug(f"Loading modified profile: {name}, picks: {self.modified[name].picks}, candidates: {self.modified[name].candidates}")
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
        # Handle initial_picks as list or dict (for backward compatibility)
        initial_picks = self.settings.value("initial_picks", [], type=list)
        if isinstance(initial_picks, dict):
            profile.initial_picks = set(initial_picks.keys())  # Convert dict to list
        else:
            profile.initial_picks = {pick for pick in initial_picks if pick}
        profile.dt = {}
        profile_dir = self.app_data_path / "profiles" / name
        # Load picks from picks.txt
        picks_file = profile_dir / "picks.txt"
        profile.picks = {}
        if picks_file.exists():
            with picks_file.open("r", encoding="utf-8") as f:
                profile.picks = {line.strip().upper() for line in f if line.strip()}
        # Load candidates from candidates.txt
        candidates_file = profile_dir / "candidates.txt"
        profile.candidates = {}
        if candidates_file.exists():
            with candidates_file.open("r", encoding="utf-8") as f:
                profile.candidates = {line.strip().upper() for line in f if line.strip()}
        # Load decision trees
        if profile_dir.exists():
            dtree_dir = profile_dir / "dtree"
            if dtree_dir.exists():
                dt_files = dtree_dir.glob("*.txt")
                profile.dt = routes_to_dt(route for file in dt_files for route in
                    read_decision_routes(file)
                )
        self.settings.endGroup()
        self.loaded[name] = profile
        return profile

    def saveProfile(self, name: str, profile: Profile):
        self.settings.beginGroup(f"profiles/{name}")
        self.settings.setValue("word_length", profile.word_length)
        self.settings.setValue("game_type", profile.game_type.value)
        self.settings.setValue("initial_picks", profile.initial_picks)  # Save as list
        self.settings.endGroup()
        self.settings.sync()


        profile_dir = self.app_data_path / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        # Save picks to picks.txt
        if profile.words_modified or profile.saved_name != name:
            with open(profile_dir / "picks.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(profile.picks)))
            # Save candidates to candidates.txt
            with open(profile_dir / "candidates.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted(profile.candidates)))
            logger.debug(f"Saved profile: {name}, initial_picks: {profile.initial_picks}, picks: {profile.picks}, candidates: {profile.candidates}")
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

        for word in save_dts:
            if word in profile.dt:
                with open(dtree_dir / f"{word}.txt", "w", encoding="utf-8") as f:
                    f.write(dt_to_text({word: profile.dt[word]}))

        profile.pending_dt_changes = {"added": set(), "deleted": set()}
        profile.dirty = False
        profile.words_modified = False

    def deleteProfile(self, name: str):
        # Mark profile for deletion instead of immediate removal

        profile = self.modified.pop(name, None) or self.loaded.pop(name, None)
        if profile:
            saved_name = profile.saved_name
        else:
            saved_name = name
        # Settings saved_name should be deleted if the profile has been renamed
        # since it was originally stored in settings
        if name not in self.to_delete:
            self.to_delete.append(saved_name)
            logger.debug(f"Marked profile {saved_name} for deletion")

        self._profile_names.remove(name)
        if name == self.current_profile:
            self.current_profile = next(iter(self._profile_names), None)
            # XXX need to do more here
        if name == self._default_profile:
            self._default_profile = self.current_profile
            logger.debug(f"Deleted default profile {name}, _default_profile set to None")

    def processDeletions(self):
        # Process all marked deletions
        for name in self.to_delete:
            logger.debug(f"Processing deletion for profile {name}")
            self.settings.beginGroup("profiles")
            self.settings.remove(name)
            self.settings.endGroup()
            profile_dir = self.app_data_path / "profiles" / name
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
                logger.debug(f"Deleted profile directory: {profile_dir}")
            # if name in self.modified: # Don't do this as a profile could be added after deleted
            #     del self.modified[name]
            # if name in self.loaded: # anyway, they should have been popped already
            #     del self.loaded[name]
        self.to_delete.clear()
        logger.debug("All marked profiles deleted")

    def modifyProfile(self, name: str, saved_name: Optional[str] = None) -> Profile:
        logger.debug(f"modifyProfile called for name: {name}, saved_name: {saved_name}")
        if name in self.modified:
            profile = self.modified[name]
            logger.debug(f"Returning existing modified profile: {name}")
            return self.modified[name]
        if saved_name and saved_name != name:
            self.to_delete.append(saved_name)
            logger.debug(f"Marked profile {saved_name} for deletion due to rename to {name}")
        if name in self.loaded:
            profile = self.loaded.pop(name)
            logger.debug(f"Popped profile from loaded: {name}")
        else:
            profile = self.loadProfile(name) if saved_name else Profile()
            logger.debug(f"Created new profile for: {name}")
        # profile.saved_name = saved_name if saved_name else name
        profile.dirty = True
        self.modified[name] = profile
        if saved_name and saved_name == self._default_profile:
            self._default_profile = name
            logger.debug(f"Default profile renamed from {saved_name} to {name}")
        return profile

    def removeDecisionTree(self, name: str, word: str):
        """Mark a decision tree for removal from a profile."""
        profile = self.modifyProfile(name)
        if word in profile.dt:
            profile.pending_dt_changes["deleted"].add(word)
            del profile.dt[word]
            profile.pending_dt_changes["added"].discard(word)
            profile.dirty = True
            logger.debug(f"Marked decision tree {word} for deletion in profile {name}")

    def addDecisionTree(self, name: str, tree_data: Dict[str, Optional[dict]]):
        """Add or update a decision tree in a profile."""
        profile = self.modifyProfile(name)

        for word in tree_data.keys():
            profile.pending_dt_changes["added"].add(word)
        for word in profile.dt.keys() & tree_data.keys():
            profile.pending_dt_changes["deleted"].add(word)
            # even it's not deleted, it would just get overwritten I think

        profile.dt.update(tree_data)

        profile.dirty = True

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
        for name, profile in self.modified.items():
            if profile.dirty:
                logger.debug(f"Saving profile: {name}, initial_picks: {profile.initial_picks}, picks: {profile.picks}, candidates: {profile.candidates}")
                self.saveProfile(name, profile)
        # Save default profile if changed
        current_default = self.settings.value("default_profile", defaultValue=None)
        if self._default_profile != current_default:
            # Validate that _default_profile exists
            valid_profiles = self.getProfileNames() + list(self.modified.keys())
            if self._default_profile is None or self._default_profile in valid_profiles:
                self.settings.setValue("default_profile", self._default_profile)
                self.settings.sync()
                logger.debug(f"Saved default profile to QSettings: {self._default_profile}")
            else:
                logger.warning(f"Invalid default profile {self._default_profile}, not saving to QSettings")
        self.modified.clear()
        logger.debug("All changes committed, cleared modified profiles")

    def discardChanges(self):
        """Discard all pending changes and reload profiles."""
        logger.debug("Discarding changes in ProfileManager")
        self.modified.clear()
        self.to_delete.clear()
        self.loaded.clear()
        self._default_profile = self.settings.value("default_profile", defaultValue=None)
        self.current_profile = self._prev_profile
        logger.debug(f"Changes discarded, default profile: {self._default_profile}, current profile: {self.current_profile}")
