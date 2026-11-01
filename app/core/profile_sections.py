"""Structured, multi-entry career profile sections.

Each section is a list of entries. The flat text fields the generation pipeline
reads (profile["experience"], ["education"], ...) are rendered from the entries.
"""
import re
from typing import Any, Dict, List

SECTION_FIELDS: Dict[str, List[str]] = {
    "experience": ["role", "company", "location", "start_date", "end_date", "description"],
    "education": ["degree", "institution", "field", "location", "start_date", "end_date", "grade", "description"],
    "certifications": ["name", "issuer", "date", "credential_url"],
    "activities": ["title", "organization", "start_date", "end_date", "description"],
}

# The field that must be non-empty for an entry to be kept.
REQUIRED_FIELD: Dict[str, str] = {
    "experience": "role",
    "education": "institution",
    "certifications": "name",
    "activities": "title",
}

ITEMS_KEY = {s: f"{s}_items" for s in SECTION_FIELDS}


def clean_items(section: str, items: List[Dict[str, Any]] | None) -> List[Dict[str, str]]:
    cleaned = []
    for raw in items or []:
        entry = {f: str(raw.get(f) or "").strip() for f in SECTION_FIELDS[section]}
        if entry[REQUIRED_FIELD[section]]:
            cleaned.append(entry)
    return cleaned


def _dates(e: Dict[str, str]) -> str:
    start, end = e.get("start_date", ""), e.get("end_date", "")
    if start and end:
        return f"{start} – {end}"
    return start or end


def _join(parts: List[str], sep: str) -> str:
    return sep.join(p for p in parts if p)


def render_text(section: str, items: List[Dict[str, str]]) -> str:
    blocks = []
    for e in items:
        if section == "experience":
            head = _join([_join([e["role"], e["company"]], " at "), e["location"], _dates(e)], " | ")
        elif section == "education":
            head = _join([_join([e["degree"], e["field"]], " in "), e["institution"], e["location"],
                          _dates(e), f"Grade: {e['grade']}" if e["grade"] else ""], " | ")
        elif section == "certifications":
            head = _join([e["name"], e["issuer"], e["date"]], " | ")
        else:
            head = _join([e["title"], e["organization"], _dates(e)], " | ")
        desc = e.get("description", "")
        blocks.append(head + ("\n" + desc if desc else ""))
    return "\n\n".join(blocks)


def seed_items(section: str, text: str) -> List[Dict[str, str]]:
    """Best-effort conversion of legacy free text into entries (one per blank-line block)."""
    text = (text or "").strip()
    if not text:
        return []
    if section == "certifications":
        items = []
        for line in (ln.strip() for ln in text.splitlines()):
            if not line:
                continue
            entry = {f: "" for f in SECTION_FIELDS[section]}
            m = re.search(r"\s*\[(https?://[^\]]+)\]\s*$", line)
            if m:
                entry["credential_url"] = m.group(1)
                line = line[: m.start()].strip()
            name, sep, issuer = line.partition(" – ")
            entry["name"], entry["issuer"] = (issuer, name) if sep else (line, "")
            items.append(entry)
        return items
    items = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        entry = {f: "" for f in SECTION_FIELDS[section]}
        entry[REQUIRED_FIELD[section]] = lines[0]
        if "description" in entry:
            entry["description"] = "\n".join(lines[1:])
        items.append(entry)
    return items


def clean_skill_groups(groups: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    out = []
    for g in groups or []:
        cat = str(g.get("category") or "").strip() or "General"
        skills, seen = [], set()
        for s in g.get("skills") or []:
            s = str(s).strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                skills.append(s)
        if skills:
            out.append({"category": cat, "skills": skills})
    return out


def flatten_skills(groups: List[Dict[str, Any]]) -> List[str]:
    flat, seen = [], set()
    for g in groups:
        for s in g["skills"]:
            if s.lower() not in seen:
                seen.add(s.lower())
                flat.append(s)
    return flat


def apply_sections(profile: Dict[str, Any], changes: Dict[str, Any]) -> None:
    """Merge structured section changes into the profile and re-render the flat fields."""
    for section in SECTION_FIELDS:
        key = ITEMS_KEY[section]
        if key in changes and changes[key] is not None:
            items = clean_items(section, changes[key])
            profile[key] = items
            profile[section] = render_text(section, items)
    if changes.get("skill_groups") is not None:
        groups = clean_skill_groups(changes["skill_groups"])
        profile["skill_groups"] = groups
        profile["skills"] = flatten_skills(groups)


def sections_view(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Structured view of the profile, seeding entries from legacy text when needed."""
    out: Dict[str, Any] = {}
    for section in SECTION_FIELDS:
        key = ITEMS_KEY[section]
        out[key] = profile.get(key) if key in profile else seed_items(section, profile.get(section, ""))
    groups = profile.get("skill_groups")
    if groups is None:
        flat = profile.get("skills", []) or []
        groups = [{"category": "General", "skills": list(flat)}] if flat else []
    out["skill_groups"] = groups
    return out
