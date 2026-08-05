import json
import os
from typing import Any, Dict, List, Optional

_PROFILE_DIR = "profiles"
_PROFILE_PATH = os.path.join(_PROFILE_DIR, "user_profile.json")
_PROJECTS_PATH = os.path.join(_PROFILE_DIR, "user_projects.json")


def save_profile(profile: Dict[str, Any]) -> None:
    os.makedirs(_PROFILE_DIR, exist_ok=True)
    with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def load_profile() -> Optional[Dict[str, Any]]:
    if not os.path.exists(_PROFILE_PATH):
        return None
    with open(_PROFILE_PATH, encoding="utf-8") as f:
        return json.load(f)


def profile_exists() -> bool:
    return os.path.exists(_PROFILE_PATH)


def save_projects(new_projects: List[Dict[str, Any]]) -> None:
    os.makedirs(_PROFILE_DIR, exist_ok=True)

    # Normalize and deduplicate so repeated parses do not inflate the project count.
    normalized: List[Dict[str, Any]] = []
    seen_titles = set()
    for project in new_projects or []:
        title = str(project.get("title", "")).strip()
        if not title:
            continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        normalized.append(project)

    with open(_PROJECTS_PATH, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2)


def load_projects() -> List[Dict[str, Any]]:
    if not os.path.exists(_PROJECTS_PATH):
        return []
    with open(_PROJECTS_PATH, encoding="utf-8") as f:
        return json.load(f)
