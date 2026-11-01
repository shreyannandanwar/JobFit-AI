"""Structured job-description extraction.

LLM extraction when configured, deterministic fallback otherwise. Every skill
carries the exact JD snippet it came from (`evidence`), and LLM output is
discarded for any skill that cannot be found in the JD text.
"""
import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Seniority = Literal["intern", "junior", "mid", "senior", "staff", "unknown"]
SENIORITY_LEVELS = ("intern", "junior", "mid", "senior", "staff")
ROLE_FAMILIES = ("backend", "frontend", "fullstack", "ml", "data", "devops", "mobile", "security", "other")


class JDExtraction(BaseModel):
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    seniority: str = "unknown"
    role_family: str = "other"
    evidence: Dict[str, str] = Field(default_factory=dict)  # skill -> exact JD snippet
    method: Literal["llm", "fallback"] = "fallback"


# canonical name -> aliases (matched case-insensitively on word boundaries)
SKILL_ALIASES: Dict[str, List[str]] = {
    "python": ["py"], "java": [], "javascript": ["js", "ecmascript", "es6"],
    "typescript": ["ts"], "go": ["golang"], "rust": [], "ruby": [], "scala": [], "kotlin": [],
    "swift": [], "php": [], "c++": ["cpp"], "c#": ["csharp", ".net", "dotnet"], "r": [],
    "react": ["react.js", "reactjs"], "next.js": ["nextjs"], "vue": ["vue.js", "vuejs"],
    "angular": ["angularjs"], "svelte": [], "html": ["html5"], "css": ["css3"],
    "tailwind": ["tailwindcss"], "redux": [],
    "node.js": ["nodejs", "node"], "express": ["express.js"], "fastapi": [], "django": [],
    "flask": [], "spring": ["spring boot", "springboot"], "rails": ["ruby on rails"],
    "graphql": [], "rest api": ["rest", "restful", "restful apis", "rest apis"], "grpc": [],
    "microservices": ["microservice"],
    "sql": [], "postgresql": ["postgres"], "mysql": [], "mongodb": ["mongo"], "redis": [],
    "elasticsearch": ["elastic"], "dynamodb": [], "cassandra": [], "sqlite": [], "snowflake": [],
    "aws": ["amazon web services"], "gcp": ["google cloud", "google cloud platform"],
    "azure": ["microsoft azure"], "docker": ["containers", "containerization"],
    "kubernetes": ["k8s"], "terraform": [], "ansible": [], "ci/cd": ["cicd", "ci cd", "continuous integration", "continuous delivery"],
    "jenkins": [], "github actions": [], "linux": [], "bash": ["shell scripting"], "git": [],
    "kafka": [], "rabbitmq": [], "spark": ["pyspark", "apache spark"], "airflow": [], "dbt": [],
    "hadoop": [], "tableau": [], "power bi": ["powerbi"], "excel": [],
    "machine learning": ["ml"], "deep learning": [], "nlp": ["natural language processing"],
    "computer vision": [], "llm": ["llms", "large language models", "large language model"],
    "generative ai": ["genai", "gen ai"], "rag": ["retrieval augmented generation", "retrieval-augmented generation"],
    "tensorflow": [], "pytorch": [], "scikit-learn": ["sklearn", "scikit learn"],
    "pandas": [], "numpy": [], "langchain": [], "langgraph": [], "openai": [],
    "hugging face": ["huggingface", "transformers"], "mlops": [],
    "streamlit": [], "pytest": [], "selenium": [], "jira": [], "agile": ["scrum"],
    "android": [], "ios": [], "react native": [], "flutter": [],
    "system design": ["distributed systems"], "data structures": ["algorithms", "dsa"],
    "oauth": [], "api": ["apis"],
}

_ALIAS_TO_CANON: Dict[str, str] = {}
for _canon, _aliases in SKILL_ALIASES.items():
    _ALIAS_TO_CANON[_canon] = _canon
    for _a in _aliases:
        _ALIAS_TO_CANON[_a.lower()] = _canon

# Short terms that only count when written exactly like this ("Go", not "go").
_CASE_SENSITIVE = {"go": "Go", "r": "R", "ml": "ML", "js": "JS", "ts": "TS", "node": "Node",
                   "spring": "Spring", "rest": "REST"}

_PATTERNS: Dict[str, "re.Pattern[str]"] = {}


def _pattern(term: str) -> "re.Pattern[str]":
    pat = _PATTERNS.get(term)
    if pat is None:
        exact = _CASE_SENSITIVE.get(term)
        if exact:
            pat = re.compile(rf"(?<![\w+#./&-]){re.escape(exact)}(?![\w+#&-]|\.\w)")
        else:
            pat = re.compile(rf"(?<![\w+#./-]){re.escape(term)}(?![\w+#]|\.\w)", re.IGNORECASE)
        _PATTERNS[term] = pat
    return pat


# Terms too ambiguous to count unless unmistakably used as the skill.
_AMBIGUOUS = {"py", "express", "transformers", "containers"}


def canonicalize(skill: str) -> str:
    key = skill.strip().lower()
    return _ALIAS_TO_CANON.get(key, key)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _find_in_line(line: str) -> List[str]:
    found: List[str] = []
    for term, canon in _ALIAS_TO_CANON.items():
        if term in _AMBIGUOUS:
            continue
        if _pattern(term).search(line) and canon not in found:
            found.append(canon)
    return found


_REQ_HEAD = re.compile(r"(requirements?|qualifications?|must[- ]haves?|what you(?:'|’)?ll need|what we(?:'|’)?re looking for|you have|you bring|skills|who you are|minimum)", re.I)
_PREF_HEAD = re.compile(r"(nice[- ]to[- ]haves?|preferred|bonus|good to have|a plus|desirable|extra credit)", re.I)
_RESP_HEAD = re.compile(r"(responsibilit|what you(?:'|’)?ll do|what you will do|the role|your role|day[- ]to[- ]day|you will|duties)", re.I)
_PREF_INLINE = re.compile(r"\b(nice to have|preferred|bonus|is a plus|are a plus|a plus|good to have|desirable)\b", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•–·]|\d+[.)])\s*")


def _split_lines(jd_text: str) -> List[tuple]:
    """Return (section, line) pairs where section is required|preferred|responsibilities|other."""
    section = "other"
    out = []
    for raw in jd_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        stripped = _BULLET.sub("", line).strip()
        is_heading = len(stripped) <= 60 and not _BULLET.match(line) and (
            stripped.endswith(":") or stripped.isupper() or len(stripped.split()) <= 5
        )
        if is_heading:
            if _PREF_HEAD.search(stripped):
                section = "preferred"; continue
            if _RESP_HEAD.search(stripped):
                section = "responsibilities"; continue
            if _REQ_HEAD.search(stripped):
                section = "required"; continue
            if stripped.endswith(":"):
                section = "other"; continue
        out.append((section, stripped))
    return out


_SENIORITY_RULES = [
    ("intern", re.compile(r"\b(intern(?:ship)?|trainee|apprentice)\b", re.I)),
    ("staff", re.compile(r"\b(staff|principal|distinguished|architect|lead engineer|engineering manager)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?|lead)\b|\b([5-9]|1\d)\+?\s*(?:\+|or more)?\s*years", re.I)),
    ("junior", re.compile(r"\b(junior|jr\.?|entry[- ]level|graduate|new grad|fresher|associate|0-2 years|1-2 years)\b", re.I)),
    ("mid", re.compile(r"\b(mid[- ]level|intermediate|[2-4]\+?\s*years)\b", re.I)),
]

_FAMILY_KEYWORDS = {
    "ml": ["machine learning", "deep learning", "nlp", "computer vision", "llm", "generative ai", "mlops", "pytorch", "tensorflow", "ml engineer", "ai engineer", "data scientist"],
    "data": ["data engineer", "data analyst", "etl", "airflow", "dbt", "spark", "snowflake", "tableau", "power bi", "analytics", "data pipeline"],
    "devops": ["devops", "sre", "site reliability", "kubernetes", "terraform", "ci/cd", "infrastructure", "platform engineer"],
    "frontend": ["frontend", "front-end", "front end", "react", "angular", "vue", "ui engineer", "css"],
    "mobile": ["android", "ios", "mobile", "flutter", "react native"],
    "security": ["security engineer", "appsec", "penetration", "infosec", "vulnerability"],
    "backend": ["backend", "back-end", "back end", "api", "microservices", "server-side", "fastapi", "django", "spring", "node.js"],
}


def _title_or_first_line(text: str, title: str) -> str:
    if title:
        return title
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first if len(first) <= 80 else ""


def infer_seniority(text: str, title: str = "") -> str:
    title = _title_or_first_line(text, title)
    haystack = f"{title}\n{text}"
    for level, pat in _SENIORITY_RULES:
        if pat.search(title or ""):
            return level
    for level, pat in _SENIORITY_RULES:
        if pat.search(haystack):
            return level
    return "unknown"


def infer_role_family(text: str, title: str = "") -> str:
    lower, title_lower = text.lower(), _title_or_first_line(text, title).lower()
    if re.search(r"full[- ]?stack", f"{title_lower} {lower}"):
        return "fullstack"
    scores = {}
    for fam, kws in _FAMILY_KEYWORDS.items():
        scores[fam] = sum(3 if kw in title_lower else 0 for kw in kws) + sum(1 for kw in kws if kw in lower)
    fam, best = max(scores.items(), key=lambda kv: kv[1])
    return fam if best > 0 else "other"


def fallback_extract(jd_text: str, role_title: str = "") -> JDExtraction:
    required: List[str] = []
    preferred: List[str] = []
    evidence: Dict[str, str] = {}
    responsibilities: List[str] = []
    qualifications: List[str] = []

    for section, line in _split_lines(jd_text):
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            is_pref = section == "preferred" or bool(_PREF_INLINE.search(sentence))
            for skill in _find_in_line(sentence):
                evidence.setdefault(skill, sentence[:240])
                bucket = preferred if is_pref else required
                if skill not in bucket:
                    bucket.append(skill)
        if section == "responsibilities" and len(line) > 15:
            responsibilities.append(line[:240])
        elif section == "required" and len(line) > 15:
            qualifications.append(line[:240])

    required_set = set(required)
    preferred = [s for s in preferred if s not in required_set]
    return JDExtraction(
        required_skills=required, preferred_skills=preferred,
        responsibilities=responsibilities[:15], qualifications=qualifications[:15],
        seniority=infer_seniority(jd_text, role_title),
        role_family=infer_role_family(jd_text, role_title),
        evidence=evidence, method="fallback",
    )


# --- LLM path ----------------------------------------------------------------

_SYSTEM = (
    "You extract structured requirements from job descriptions. Respond with JSON only. "
    "Never invent skills: every skill must be explicitly present in the job description."
)

_PROMPT = """Extract from the job description below. Return JSON with exactly these keys:
required_skills: list of technical skills the JD requires
preferred_skills: list of skills marked nice-to-have / preferred / bonus
responsibilities: list of short responsibility statements
qualifications: list of non-skill qualifications (degree, years of experience)
seniority: one of {seniority}
role_family: one of {families}
evidence: object mapping EVERY skill to an exact, verbatim snippet (max 200 chars) copied from the JD

Job description:
\"\"\"
{jd}
\"\"\""""


def _parse_json(raw: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _locate_snippet(snippet: str, jd_flat: str) -> bool:
    return bool(snippet) and _squash(snippet).lower() in jd_flat


def _snippet_for(skill: str, jd_text: str) -> Optional[str]:
    terms = [t for t, c in _ALIAS_TO_CANON.items() if c == skill and t not in _AMBIGUOUS] or [skill]
    for _, line in _split_lines(jd_text):
        if any(_pattern(t).search(line) for t in terms):
            return line[:240]
    return None


def _validate_llm(data: dict, jd_text: str) -> Optional[JDExtraction]:
    jd_flat = _squash(jd_text).lower()
    evidence_in = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    evidence_in = {canonicalize(str(k)): str(v) for k, v in evidence_in.items()}
    evidence: Dict[str, str] = {}

    def clean(key: str) -> List[str]:
        out: List[str] = []
        for raw in data.get(key) or []:
            skill = canonicalize(str(raw))
            if not skill or skill in out:
                continue
            snippet = evidence_in.get(skill, "")
            if _locate_snippet(snippet, jd_flat):
                evidence[skill] = _squash(snippet)
            else:
                found = _snippet_for(skill, jd_text)
                if not found:
                    continue  # cannot be grounded in the JD: drop it
                evidence[skill] = found
            out.append(skill)
        return out

    required = clean("required_skills")
    preferred = [s for s in clean("preferred_skills") if s not in required]
    if not required and not preferred:
        return None

    def text_list(key: str) -> List[str]:
        return [_squash(str(x))[:240] for x in (data.get(key) or []) if str(x).strip()][:15]

    seniority = str(data.get("seniority", "")).lower()
    family = str(data.get("role_family", "")).lower()
    return JDExtraction(
        required_skills=required, preferred_skills=preferred,
        responsibilities=text_list("responsibilities"), qualifications=text_list("qualifications"),
        seniority=seniority if seniority in SENIORITY_LEVELS else infer_seniority(jd_text),
        role_family=family if family in ROLE_FAMILIES else infer_role_family(jd_text),
        evidence=evidence, method="llm",
    )


def jd_hash(jd_text: str) -> str:
    return hashlib.sha256(_squash(jd_text).encode("utf-8")).hexdigest()


def _cache_key(jd_text: str, llm_cfg: Dict[str, Any]) -> str:
    return f"{jd_hash(jd_text)}:{llm_cfg.get('provider')}:{llm_cfg.get('model') or ''}"


def _cache_get(key: str) -> Optional[JDExtraction]:
    from app.core.memory import get_db
    with get_db() as conn:
        row = conn.execute("SELECT payload FROM jd_extractions WHERE cache_key = ?", (key,)).fetchone()
    if not row:
        return None
    try:
        return JDExtraction.model_validate_json(row["payload"])
    except ValueError:
        return None


def _cache_put(key: str, result: JDExtraction) -> None:
    from app.core.memory import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO jd_extractions (cache_key, payload, created_at) VALUES (?, ?, ?)",
            (key, result.model_dump_json(), datetime.now().isoformat()),
        )
        conn.commit()


def extract_jd(jd_text: str, llm_cfg: Optional[Dict[str, Any]] = None, role_title: str = "") -> JDExtraction:
    """LLM extraction (cached by JD hash) when configured; deterministic fallback otherwise or on failure."""
    llm_cfg = llm_cfg or {}
    if not llm_cfg.get("provider") or not jd_text.strip():
        return fallback_extract(jd_text, role_title)

    key = _cache_key(jd_text, llm_cfg)
    cached = _cache_get(key)
    if cached:
        return cached

    from app.core.llm import llm_chat
    prompt = _PROMPT.format(seniority=" | ".join(SENIORITY_LEVELS), families=" | ".join(ROLE_FAMILIES), jd=jd_text[:12000])
    raw = llm_chat([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}],
                   llm_cfg, temperature=0.0, max_tokens=2000)
    data = _parse_json(raw) if raw else None
    result = _validate_llm(data, jd_text) if data else None
    if result is None:
        return fallback_extract(jd_text, role_title)
    _cache_put(key, result)
    return result
