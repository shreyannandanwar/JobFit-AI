"""Content contract — Pydantic models that define the exact data shape the
resume layout engine consumes.

Everything the layout needs flows through ``ResumeLayoutInput``; no flat-text
fields, no ad-hoc dicts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Structured profile entries ────────────────────────────────────────────────

class ContactInfo(BaseModel):
    name: str = "Your Name"
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""


class ExperienceEntry(BaseModel):
    id: str = ""
    role: str = ""
    company: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""


class ProjectEntry(BaseModel):
    id: str = ""
    title: str = ""
    description: str = ""
    technologies: List[str] = Field(default_factory=list)
    github: str = ""
    deployment: str = ""


class EducationEntry(BaseModel):
    institution: str = ""
    degree: str = ""
    field: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""
    description: str = ""


# ── Content produced by the tailoring pipeline ────────────────────────────────

class ResumeContent(BaseModel):
    """Tailored content that the LLM / tailoring nodes produced."""
    summary: str = ""
    highlights: List[str] = Field(default_factory=list)
    experience_notes: Dict[str, List[str]] = Field(
        default_factory=dict,
        description=(
            "Extra tailored bullets keyed by ExperienceEntry.id.  "
            "The layout merges these with the entry's own description."
        ),
    )
    projects_used: List[str] = Field(
        default_factory=list,
        description="IDs of the projects to include (subset of all projects).",
    )
    skills_grouped: Dict[str, List[str]] = Field(
        default_factory=dict,
        description=(
            "Pre-grouped skills.  If empty the layout will auto-group "
            "from the raw skill list via normalize_skills()."
        ),
    )


# ── Top-level input to the layout engine ──────────────────────────────────────

class ResumeLayoutInput(BaseModel):
    """Everything the DOCX layout engine needs — no more, no less."""
    contact: ContactInfo = Field(default_factory=ContactInfo)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    activities: List[str] = Field(default_factory=list)
    raw_skills: List[str] = Field(
        default_factory=list,
        description="Flat skill tokens extracted from the profile (may be messy).",
    )
    content: ResumeContent = Field(default_factory=ResumeContent)


# ── Helper: build a ResumeLayoutInput from a legacy profile dict ──────────────

def _generate_id(prefix: str, index: int) -> str:
    return f"{prefix}_{index}"


def layout_input_from_profile(
    profile: Dict[str, Any],
    tailored_bullets: List[str] | None = None,
) -> ResumeLayoutInput:
    """Convert the existing ``profile`` dict + ``tailored_bullets`` list into a
    fully-typed ``ResumeLayoutInput``.

    This bridge keeps the LangGraph nodes and prompts unchanged — the
    ``docx_export_node`` calls this converter before handing data to the
    layout engine.
    """
    from app.core.profile_sections import seed_items, SECTION_FIELDS

    # ── Contact ───────────────────────────────────────────────────────────
    contact = ContactInfo(
        name=profile.get("name", "Your Name"),
        email=profile.get("email", ""),
        phone=profile.get("phone", ""),
        linkedin=profile.get("linkedin", ""),
        github=profile.get("github", ""),
        location=profile.get("location", ""),
    )

    # ── Experience ────────────────────────────────────────────────────────
    exp_items = profile.get("experience_items") or seed_items(
        "experience", profile.get("experience", "")
    )
    experience: List[ExperienceEntry] = []
    for i, e in enumerate(exp_items):
        experience.append(ExperienceEntry(
            id=_generate_id("exp", i),
            role=e.get("role", ""),
            company=e.get("company", ""),
            location=e.get("location", ""),
            start_date=e.get("start_date", ""),
            end_date=e.get("end_date", ""),
            description=e.get("description", ""),
        ))

    # ── Education ─────────────────────────────────────────────────────────
    edu_items = profile.get("education_items") or seed_items(
        "education", profile.get("education", "")
    )
    education: List[EducationEntry] = []
    for e in edu_items:
        education.append(EducationEntry(
            institution=e.get("institution", ""),
            degree=e.get("degree", ""),
            field=e.get("field", ""),
            location=e.get("location", ""),
            start_date=e.get("start_date", ""),
            end_date=e.get("end_date", ""),
            grade=e.get("grade", ""),
            description=e.get("description", ""),
        ))

    # ── Projects ──────────────────────────────────────────────────────────
    project_list: List[Dict[str, Any]] = profile.get("project_list", [])
    projects: List[ProjectEntry] = []
    for i, p in enumerate(project_list):
        projects.append(ProjectEntry(
            id=_generate_id("proj", i),
            title=p.get("title", ""),
            description=p.get("description", ""),
            technologies=p.get("technologies", []),
            github=p.get("github", ""),
            deployment=p.get("deployment", ""),
        ))

    # ── Certifications ────────────────────────────────────────────────────
    cert_items = profile.get("certifications_items") or seed_items(
        "certifications", profile.get("certifications", "")
    )
    certifications: List[str] = []
    for c in cert_items:
        if isinstance(c, str):
            c_str = c.strip()
            if c_str:
                certifications.append(c_str)
        elif isinstance(c, dict):
            issuer = str(c.get("issuer") or "").strip()
            name = str(c.get("name") or "").strip()
            if issuer and name:
                certifications.append(f"{issuer} – {name}")
            elif name or issuer:
                certifications.append(name or issuer)

    # ── Activities ────────────────────────────────────────────────────────
    act_items = profile.get("activities_items") or seed_items(
        "activities", profile.get("activities", "")
    )
    activities: List[str] = []
    for a in act_items:
        if isinstance(a, str):
            a_str = a.strip()
            if a_str:
                activities.append(a_str)
        elif isinstance(a, dict):
            title = str(a.get("title") or "").strip()
            org = str(a.get("organization") or "").strip()
            if title and org:
                activities.append(f"{title} ({org})")
            elif title or org:
                activities.append(title or org)

    # ── Skills (raw) ──────────────────────────────────────────────────────
    raw_skills: List[str] = profile.get("skills", [])

    # ── Content from tailored_bullets ─────────────────────────────────────
    summary = ""
    highlights: List[str] = []
    if tailored_bullets:
        summary = tailored_bullets[0]
        highlights = list(tailored_bullets[1:4])

    content = ResumeContent(
        summary=summary,
        highlights=highlights,
        projects_used=[p.id for p in projects],  # include all by default
    )

    return ResumeLayoutInput(
        contact=contact,
        experience=experience,
        projects=projects,
        education=education,
        certifications=certifications,
        activities=activities,
        raw_skills=raw_skills,
        content=content,
    )

