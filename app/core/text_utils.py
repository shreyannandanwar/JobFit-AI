"""Skills normalisation and text-cleaning utilities for resume layout.

Pure functions — no LLM calls, no network, no side effects.
"""

import re
from typing import Dict, List

# ── Abbreviation expansion table ──────────────────────────────────────────────
# Keys are lowercase tokens; values are their properly-cased expansions.
_ABBREVIATIONS: Dict[str, str] = {
    "ml": "Machine Learning",
    "dl": "Deep Learning",
    "ai": "Artificial Intelligence",
    "nlp": "Natural Language Processing",
    "cv": "Computer Vision",
    "api": "REST APIs",
    "apis": "REST APIs",
    "rest": "REST APIs",
    "js": "JavaScript",
    "ts": "TypeScript",
    "py": "Python",
    "db": "Databases",
    "dbs": "Databases",
    "k8s": "Kubernetes",
    "tf": "Terraform",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "oop": "Object-Oriented Programming",
    "os": "Operating Systems",
    "aws": "AWS",
    "gcp": "Google Cloud Platform",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "llm": "Large Language Models",
    "llms": "Large Language Models",
    "etl": "ETL Pipelines",
    "devops": "DevOps",
    "qa": "Quality Assurance",
    "ui": "UI Development",
    "ux": "UX Design",
}

# ── Default skill grouping buckets ────────────────────────────────────────────
_GROUP_KEYWORDS: Dict[str, List[str]] = {
    "Languages": [
        "python", "java", "javascript", "typescript", "c++", "c#", "go",
        "rust", "ruby", "scala", "kotlin", "swift", "php", "r", "matlab",
        "bash", "shell", "perl", "lua", "dart",
    ],
    "Frameworks & Libraries": [
        "react", "angular", "vue", "next.js", "django", "flask", "fastapi",
        "spring", "spring boot", "express", "node.js", "rails",
        "tensorflow", "pytorch", "keras", "scikit-learn", "pandas", "numpy",
        "langchain", "langgraph", "streamlit", "jquery", "bootstrap",
    ],
    "Cloud & DevOps": [
        "aws", "google cloud platform", "azure", "docker", "kubernetes",
        "terraform", "ansible", "ci/cd", "devops", "jenkins", "github actions",
        "linux", "nginx",
    ],
    "Data & Databases": [
        "sql", "postgresql", "mongodb", "redis", "mysql", "sqlite",
        "elasticsearch", "cassandra", "dynamodb", "firebase", "neo4j",
        "etl pipelines", "spark", "kafka", "airflow", "snowflake",
        "databases",
    ],
    "AI & Machine Learning": [
        "machine learning", "deep learning", "natural language processing",
        "computer vision", "artificial intelligence", "large language models",
        "openai", "hugging face",
    ],
    "Tools & Practices": [
        "git", "rest apis", "graphql", "agile", "scrum", "jira",
        "object-oriented programming", "html", "css", "ui development",
        "ux design", "quality assurance", "figma",
    ],
}

# Maximum items in the final skills section (across all groups).
_MAX_TOTAL_SKILLS = 12
_MAX_GROUPS = 2


def _title_case_skill(skill: str) -> str:
    """Title-case a skill token, preserving acronyms and special casing."""
    # Already expanded / well-known → leave as-is.
    if skill in {v for v in _ABBREVIATIONS.values()}:
        return skill

    # Fully uppercase short tokens are likely acronyms.
    if skill.isupper() and len(skill) <= 5:
        return skill

    # Contains dots or slashes → leave mostly untouched but capitalise first letter.
    if "." in skill or "/" in skill:
        return skill[0].upper() + skill[1:] if skill else skill

    return skill.title()


def normalize_skills(skills: List[str]) -> Dict[str, List[str]]:
    """Deduplicate, expand abbreviations, title-case, and bucket skills.

    Returns a dict of ``{group_name: [skill, …]}`` with at most
    ``_MAX_GROUPS`` groups and ``_MAX_TOTAL_SKILLS`` items total.
    """
    # 1. Expand, title-case, dedupe (preserving first-seen order).
    seen: set[str] = set()
    expanded: List[str] = []
    for raw in skills:
        token = raw.strip()
        if not token:
            continue
        key = token.lower()
        # Expand known abbreviations.
        resolved = _ABBREVIATIONS.get(key, _title_case_skill(token))
        dedup_key = resolved.lower()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        expanded.append(resolved)

    # 2. Bucket into groups.
    grouped: Dict[str, List[str]] = {}
    ungrouped: List[str] = []
    for skill in expanded:
        placed = False
        for group_name, keywords in _GROUP_KEYWORDS.items():
            if skill.lower() in keywords:
                grouped.setdefault(group_name, []).append(skill)
                placed = True
                break
        if not placed:
            ungrouped.append(skill)

    # 3. Pick the top groups (by item count) and merge the rest into a catch-all.
    if ungrouped:
        grouped.setdefault("Other", []).extend(ungrouped)

    sorted_groups = sorted(grouped.items(), key=lambda kv: len(kv[1]), reverse=True)

    # Keep at most _MAX_GROUPS.  Overflow groups are merged into the last
    # kept group so that important skills (like "Machine Learning") are
    # never silently dropped.
    result: Dict[str, List[str]] = {}
    overflow: List[str] = []
    for i, (name, items) in enumerate(sorted_groups):
        if i < _MAX_GROUPS:
            result[name] = list(items)
        else:
            overflow.extend(items)

    # Distribute overflow items: insert at the front of each group
    # (round-robin by smallest) so they survive the cap.
    if overflow and result:
        sorted_result_keys = sorted(result.keys(), key=lambda k: len(result[k]))
        for item in overflow:
            target = sorted_result_keys[0]
            result[target].insert(0, item)
            sorted_result_keys.sort(key=lambda k: len(result[k]))

    # Enforce _MAX_TOTAL_SKILLS cap — trim from the END of each group.
    total = sum(len(v) for v in result.values())
    while total > _MAX_TOTAL_SKILLS and result:
        # Pop from the longest group.
        longest = max(result, key=lambda k: len(result[k]))
        result[longest].pop()  # remove last item
        total -= 1

    # If nothing survived, return a single "Technical Skills" bucket.
    if not result and expanded:
        result["Technical Skills"] = expanded[:_MAX_TOTAL_SKILLS]

    return result


def clean_text(s: str) -> str:
    """Normalise a single text string for resume display.

    • Collapse multiple whitespace characters into a single space.
    • Strip trailing fragment markers ("...", orphaned "--").
    • Sentence-capitalise (first letter uppercase).
    • Ensure the string ends with appropriate punctuation.
    """
    if not s:
        return ""

    text = s.strip()
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text)
    # Strip trailing truncation / fragment markers.
    text = re.sub(r"[\.\s]*\.{3,}\s*$", "", text)      # trailing "..."
    text = re.sub(r"\s*--\s*$", "", text)                # trailing " --"
    text = re.sub(r"\s*–\s*$", "", text)                 # trailing " –"
    # Strip leading bullets / dashes that the layout will supply.
    text = re.sub(r"^[-•*–]\s*", "", text)
    text = text.strip()
    if not text:
        return ""
    # Sentence-capitalise.
    text = text[0].upper() + text[1:]
    # Ensure ending punctuation for bullet-style text.
    if text[-1] not in ".!?:":
        text += "."
    return text
