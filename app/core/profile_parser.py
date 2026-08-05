import re
from typing import Any, Dict, List, Optional

SECTION_PATTERNS = {
    "education": r"\b(?:education|academic|qualification|degree)\b",
    "experience": r"\b(?:experience|employment|work history|professional)\b",
    "certifications": r"\b(?:certif|licens|course|training)\b",
    "projects": r"\b(?:projects|portfolio|work samples)\b",
    "activities": r"\b(?:activities|volunteer|leadership|extracurricular|community)\b",
    "skills": r"\b(?:skills|technologies|tools|competencies|proficiency)\b",
    "summary": r"\b(?:summary|objective|about|profile)\b",
}

TECH_SKILLS = [
    "python", "java", "javascript", "typescript", "react", "node.js", "docker",
    "kubernetes", "aws", "gcp", "azure", "sql", "postgresql", "mongodb", "redis",
    "fastapi", "django", "flask", "machine learning", "deep learning", "tensorflow",
    "pytorch", "pandas", "numpy", "scikit-learn", "git", "linux", "ci/cd",
    "langgraph", "langchain", "openai", "streamlit", "html", "css", "c++", "c#",
    "go", "rust", "ruby", "scala", "spark", "kafka", "rest api", "graphql",
    "next.js", "vue", "angular", "spring", "terraform", "ansible", "bash",
]


def extract_profile(resume_text: str) -> Dict[str, Any]:
    lines = [l.strip() for l in resume_text.strip().splitlines() if l.strip()]
    profile: Dict[str, Any] = {
        "name": _extract_name(lines),
        "phone": _extract_phone(resume_text),
        "email": _extract_email(resume_text),
        "linkedin": _extract_linkedin(resume_text),
        "github": _extract_github(resume_text),
        "skills": _extract_skills(resume_text),
        "education": "",
        "experience": "",
        "certifications": "",
        "projects": "",
        "activities": "",
        "summary": "",
    }
    for key, content in _split_into_sections(lines).items():
        if key in profile:
            profile[key] = content
    return profile


def _extract_name(lines: List[str]) -> str:
    for line in lines[:5]:
        if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$", line):
            return line
    return lines[0] if lines else "Unknown"


def _extract_phone(text: str) -> str:
    match = re.search(r"(\+?\d[\d\s\-().]{7,15}\d)", text)
    return match.group(1).strip() if match else ""


def _extract_email(text: str) -> str:
    match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return match.group(0) if match else ""


def _extract_linkedin(text: str) -> str:
    match = re.search(
        r"(?:https?://)?(?:www\.)?(linkedin\.com/in/[A-Za-z0-9_\-]+/?)",
        text, re.IGNORECASE,
    )
    return f"https://{match.group(1)}" if match else ""


def _extract_github(text: str) -> str:
    match = re.search(
        r"(?:https?://)?(?:www\.)?(github\.com/[A-Za-z0-9_\-]+)(?:/[A-Za-z0-9_\-]+)?",
        text, re.IGNORECASE,
    )
    return f"https://{match.group(1)}" if match else ""


def _extract_skills(text: str) -> List[str]:
    lower = text.lower()
    return [s for s in TECH_SKILLS if s in lower]


def _detect_section(line: str) -> Optional[str]:
    lower = line.lower().strip(" :-\t|")
    if not re.match(r"^.{0,40}$", lower):
        return None
    for section, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, lower):
            return section
    return None


def _split_into_sections(lines: List[str]) -> Dict[str, str]:
    sections: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in lines:
        detected = _detect_section(line)
        if detected:
            current = detected
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


# =============================================================================
# PROJECT PARSER  (free-form text → structured list)
# =============================================================================

def _is_project_title_line(lines: List[str], index: int) -> bool:
    s = lines[index].strip()
    if not s:
        return False

    # Only treat explicit project-title markers as section starts.
    # Examples: "Project 1", "Project Title: Foo", "## Project title: Foo".
    if re.match(r"^(?:#{1,3}\s*)?(?:project(?:\s+title)?(?:\s+\d+)?|project)\b", s, re.I):
        if re.search(r"[:\-]", s) or re.search(r"\bproject\s+\d+\b", s, re.I):
            return True
        if re.fullmatch(r"(?:#{1,3}\s*)?(?:project(?:\s+title)?(?:\s+\d+)?|project)", s, re.I):
            return True
        return bool(re.match(r"^(?:#{1,3}\s*)?(?:project(?:\s+title)?(?:\s+\d+)?|project)\s*$", s, re.I))

    return False


def parse_projects_text(text: str) -> List[Dict[str, Any]]:
    """Parse free-form text (resume section, paste, extracted doc) into project dicts."""
    if not text or not text.strip():
        return []

    lines = [l.rstrip() for l in text.splitlines()]

    # Find candidate project start lines. We only split on explicit project-title markers or
    # on headings that look like project titles and are followed by project evidence.
    block_starts: List[int] = []
    for idx, line in enumerate(lines):
        if idx == 0 or _is_project_title_line(lines, idx):
            block_starts.append(idx)

    if not block_starts:
        block_starts = [0]

    projects = []
    seen_titles = set()
    for idx, start in enumerate(block_starts):
        end = block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines)
        block = [l for l in lines[start:end] if l.strip()]
        if not block:
            continue

        title = lines[start].strip()
        title = re.sub(r"^#{1,3}\s*", "", title)
        title = re.sub(r"^(?:project(?: title)?|project\s+\d+|project)\s*[:\-]?\s*", "", title, flags=re.I)
        title = title.strip(" :-")

        proj = _parse_project_block(block, fallback_title=title or None)
        title_value = (proj.get("title") or "").strip()
        if not title_value:
            continue
        key = title_value.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        projects.append(proj)
    return projects


def _parse_project_block(lines: List[str], fallback_title: str | None = None) -> Dict[str, Any]:
    # Clean heading markers from the title line.
    raw_title = lines[0].strip() if lines else (fallback_title or "")
    title = re.sub(r"^#{1,3}\s+", "", raw_title)
    title = re.sub(r"^\d+[\.\)]\s+", "", title)
    title = re.sub(r"^\*\*(.+)\*\*$", r"\1", title)
    title = re.sub(r"^project(?: title)?\s*:\s*", "", title, flags=re.I)
    title = title.strip(" :-")

    if not title and fallback_title:
        title = fallback_title.strip(" :-")

    github = ""
    deployment = ""
    technologies: List[str] = []
    desc_lines: List[str] = []

    tech_prefixes = ("tech", "stack", "built with", "technologies", "tools", "languages", "framework")

    for line in lines[1:]:
        s = line.strip()
        lo = s.lower()
        if not s or s == "---":
            continue

        # GitHub URL
        gh = re.search(r"https?://(?:www\.)?github\.com/[A-Za-z0-9_.%+\-/]+", s, re.I)
        if gh and not github:
            github = gh.group(0).rstrip(".,)")

        # Other URL (demo / deployment)
        url = re.search(r"https?://\S+", s, re.I)
        if url:
            u = url.group(0).rstrip(".,)")
            if not re.search(r"github\.com", u, re.I) and not deployment:
                deployment = u

        # Tech line: "Tech: Python, React" or "- Technologies: ..."
        if any(lo.lstrip("-* ").startswith(p) for p in tech_prefixes):
            part = re.sub(r"^[^:]+:\s*", "", s)
            part = re.sub(r"^[-*]\s*", "", part)
            technologies = [t.strip() for t in re.split(r"[,|/]", part) if t.strip()]
        elif not re.match(r"^[-*]\s*(github|demo|live|link|deploy)", lo):
            # Avoid duplicating URL-only lines
            if not re.match(r"^https?://", s):
                desc_lines.append(s.lstrip("-* "))

    return {
        "title": title,
        "description": " ".join(desc_lines).strip(),
        "github": github,
        "deployment": deployment,
        "technologies": technologies,
    }
