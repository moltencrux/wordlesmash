from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
from PyQt6.QtCore import QStandardPaths
from .tree_utils import routes_to_dt, read_decision_routes, dt_to_text
import logging

logger = logging.getLogger(__name__)

class GameType(Enum):
    WORDLE = "wordle"
    NYT_NORMAL = "NYT - Normal Mode"
    OTHER = "other"

@dataclass
class Profile:
    word_length: int = 5
    dt: Dict[str, str] = field(default_factory=dict)  # {pick: path to dtree/<pick>.txt}
    game_type: GameType = GameType.WORDLE
    candidates: List[str] = field(default_factory=list)
    picks: List[str] = field(default_factory=list)
    initial_picks: List[str] = field(default_factory=list)  # {pick: status}
    original_name: Optional[str] = None
    dirty: bool = False

class ProfileManager:
    def __init__(self, parent=None, settings=None):
        self.settings = settings if settings is not None else QSettings()
        self.app_data_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self._app_cache_path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
        self.modified: Dict[str, Profile] = {}
        self.loaded: Dict[str, Profile] = {}
        self.to_delete: List[str] = []  # Track profiles to delete on OK/Apply
        self._default_profile = self.settings.value("default_profile", defaultValue=None)
        self.current_profile = self.getDefaultProfile()

    def getCurrentProfile(self) -> Optional[str]:
        return self.current_profile

    def setCurrentProfile(self, name: str):
        self.current_profile = name
        logger.debug(f"Set current profile: {name}")

    def getDefaultProfile(self) -> Optional[str]:
        return self._default_profile

    def setDefaultProfile(self, name: str):
        self._default_profile = name

    def getProfileNames(self) -> List[str]:
        self.settings.beginGroup("profiles")
        names = self.settings.childGroups()
        self.settings.endGroup()
        return names

    def getPicks(self) -> List[str]:
        profile = self.loadProfile(self.current_profile)
        return profile.picks

    def getCandidates(self) -> List[str]:
        profile = self.loadProfile(self.current_profile)
        return profile.candidates

    def getDecisionTrees(self):
        profile = self.getCurrentProfile()
        profile_dir = Path(self.app_data_path) / "profiles" / profile
        dtree_dir = profile_dir / "dtree"
        return tuple(dtree_dir.glob("*.txt"))

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
        self.settings.beginGroup(f"profiles/{name}")
        profile.word_length = int(self.settings.value("word_length", 5))
        profile.game_type = GameType(self.settings.value("game_type", GameType.WORDLE.value))
        # Handle initial_picks as list or dict (for backward compatibility)
        initial_picks = self.settings.value("initial_picks", [], type=list)
        if isinstance(initial_picks, dict):
            profile.initial_picks = list(initial_picks.keys())  # Convert dict to list
        else:
            profile.initial_picks = [pick for pick in initial_picks if pick]
        profile.dt = {}
        profile_dir = self.app_data_path / "profiles" / name
        # Load picks from picks.txt
        picks_file = profile_dir / "picks.txt"
        profile.picks = []
        if picks_file.exists():
            with picks_file.open("r", encoding="utf-8") as f:
                profile.picks = [line.strip().upper() for line in f if line.strip()]
        # Load candidates from candidates.txt
        candidates_file = profile_dir / "candidates.txt"
        profile.candidates = []
        if candidates_file.exists():
            with candidates_file.open("r", encoding="utf-8") as f:
                profile.candidates = [line.strip().upper() for line in f if line.strip()]
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
        with open(profile_dir / "picks.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(profile.picks))
        # Save candidates to candidates.txt
        with open(profile_dir / "candidates.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(profile.candidates))
        logger.debug(f"Saved profile: {name}, initial_picks: {profile.initial_picks}, picks: {profile.picks}, candidates: {profile.candidates}")
        dtree_dir = profile_dir / "dtree"
        dtree_dir.mkdir(parents=True, exist_ok=True)
        for word, subtree in profile.dt.items():
            with open(dtree_dir / f"{word}.txt", "w", encoding="utf-8") as f:
                f.write(dt_to_text({word: subtree}))

    def deleteProfile(self, name: str):
        # Mark profile for deletion instead of immediate removal
        if name not in self.to_delete:
            self.to_delete.append(name)
            logger.debug(f"Marked profile {name} for deletion")
        if name == self.current_profile:
            self.current_profile = None
        if name == self._default_profile:
            self._default_profile = None
            logger.debug(f"Deleted default profile {name}, _default_profile set to None")

    def processDeletions(self):
        # Process all marked deletions
        for name in self.to_delete:
            logger.debug(f"Processing deletion for profile {name}")
            self.settings.beginGroup("profiles")
            self.settings.remove(name)
            self.settings.endGroup()
            self.settings.sync()
            profile_dir = self.app_data_path / "profiles" / name
            if profile_dir.exists():
                shutil.rmtree(profile_dir)
            if name in self.modified:
                del self.modified[name]
            if name in self.loaded:
                del self.loaded[name]
        self.to_delete.clear()
        logger.debug("All marked profiles deleted")

    def modifyProfile(self, name: str, original_name: Optional[str] = None) -> Profile:
        logger.debug(f"modifyProfile called for name: {name}, original_name: {original_name}")
        if name in self.modified:
            profile = self.modified[name]
            logger.debug(f"Returning existing modified profile: {name}")
        else:
            if name in self.loaded:
                profile = self.loaded.pop(name)
                logger.debug(f"Popped profile from loaded: {name}")
            else:
                profile = self.loadProfile(name) if original_name else Profile()
                logger.debug(f"Created new profile for: {name}")
            profile.original_name = original_name if original_name else name
            profile.dirty = True
            self.modified[name] = profile
        # Update _default_profile if renaming the default profile
        if original_name and original_name == self._default_profile:
            self._default_profile = name
            logger.debug(f"Default profile renamed from {original_name} to {name}")
        return profile

    def has_pending_changes(self) -> bool:
        """Check if there are any pending changes to profiles or default profile."""
        current_default = self.settings.value("default_profile", defaultValue=None)
        default_changed = self._default_profile != current_default
        return bool(self.modified or self.to_delete or default_changed)

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
