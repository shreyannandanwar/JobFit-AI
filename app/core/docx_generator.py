"""Resume and cover-letter DOCX generation.

The resume layout engine is a pure function: no LLM calls, no network, no I/O
besides writing the output file.  All data arrives via ``ResumeLayoutInput``.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from app.core.content_contract import (
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    ResumeLayoutInput,
)
from app.core.text_utils import clean_text, normalize_skills

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DIR = _PROJECT_ROOT / "output" / "generated"

# ── Typography constants ──────────────────────────────────────────────────────
_FONT_FAMILY = "Calibri"
_NAME_SIZE = Pt(18)
_CONTACT_SIZE = Pt(9)
_SECTION_HEADING_SIZE = Pt(11)
_BODY_SIZE = Pt(10)
_LINE_SPACING = 1.15
_MARGIN = Inches(0.6)
_GRAY = RGBColor(0x66, 0x66, 0x66)

# High-school equivalent markers — omit these when a degree is present.
_HIGHSCHOOL_MARKERS = re.compile(
    r"\b(high\s*school|hsc|ssc|10th|12th|intermediate|secondary|sr\.?\s*sec|higher\s*sec|cbse|icse|isc)\b",
    re.IGNORECASE,
)

# Degree-level markers.
_DEGREE_MARKERS = re.compile(
    r"\b(b\.?\s*tech|b\.?\s*e\.?|b\.?\s*sc|b\.?\s*s\.?|m\.?\s*tech|m\.?\s*s\.?|m\.?\s*sc|"
    r"bachelor|master|ph\.?\s*d|diploma|associate|mba|bca|mca|b\.?\s*a\.?|m\.?\s*a\.?)\b",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _set_font(run, size=_BODY_SIZE, bold=False, italic=False, color=None, all_caps=False):
    """Apply font properties to a run."""
    run.font.name = _FONT_FAMILY
    run.font.size = size
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = color
    if all_caps:
        run.font.all_caps = True
    # Ensure Calibri is used for East-Asian fallback as well.
    r_elem = run._element
    rPr = r_elem.find(qn("w:rPr"))
    if rPr is None:
        rPr = r_elem.makeelement(qn("w:rPr"), {})
        r_elem.insert(0, rPr)
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(qn("w:rFonts"), {})
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), _FONT_FAMILY)
    rFonts.set(qn("w:hAnsi"), _FONT_FAMILY)


def _set_paragraph_spacing(para, before=0, after=0, line_spacing=None):
    """Set spacing on a paragraph."""
    pf = para.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line_spacing:
        pf.line_spacing = line_spacing


def _add_section_heading(doc: Document, text: str) -> None:
    """Add a styled section heading with a thin bottom rule."""
    para = doc.add_paragraph()
    _set_paragraph_spacing(para, before=6, after=3)
    run = para.add_run(text.upper())
    _set_font(run, size=_SECTION_HEADING_SIZE, bold=True, all_caps=True)

    # Thin bottom border via XML.
    pPr = para._element.get_or_add_pPr()
    pBdr = pPr.makeelement(qn("w:pBdr"), {})
    bottom = pBdr.makeelement(qn("w:bottom"), {
        qn("w:val"): "single",
        qn("w:sz"): "4",
        qn("w:space"): "1",
        qn("w:color"): "999999",
    })
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_body_paragraph(doc: Document, text: str, bold=False, italic=False) -> None:
    """Add a plain body paragraph (never truncated)."""
    para = doc.add_paragraph()
    _set_paragraph_spacing(para, line_spacing=_LINE_SPACING)
    run = para.add_run(text)
    _set_font(run, bold=bold, italic=italic)


def _add_bullet(doc: Document, text: str) -> None:
    """Add an en-dash bullet paragraph."""
    cleaned = clean_text(text)
    if not cleaned:
        return
    para = doc.add_paragraph()
    _set_paragraph_spacing(para, line_spacing=_LINE_SPACING)
    run = para.add_run(f"\u2013 {cleaned}")  # en-dash
    _set_font(run)


def _has_degree(entries: List[EducationEntry]) -> bool:
    """Return True if any education entry looks like a degree-level qualification."""
    for e in entries:
        combined = f"{e.degree} {e.field} {e.institution} {e.description}"
        if _DEGREE_MARKERS.search(combined):
            return True
    return False


def _is_highschool(entry: EducationEntry) -> bool:
    """Return True if the entry looks like a high-school / 10+2 entry."""
    combined = f"{entry.degree} {entry.field} {entry.institution} {entry.description}"
    return bool(_HIGHSCHOOL_MARKERS.search(combined))


def _format_date_range(start: str, end: str) -> str:
    """Format a date range, e.g. 'Jan. 2020–Dec. 2022'."""
    parts = []
    if start:
        parts.append(start)
    if end:
        parts.append(end)
    return "\u2013".join(parts) if parts else ""


def _ensure_output_dir(path: str | os.PathLike[str]) -> str:
    path_obj = Path(path)
    if not path_obj.is_absolute():
        path_obj = _PROJECT_ROOT / path_obj
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    return str(path_obj)


# ═══════════════════════════════════════════════════════════════════════════════
# RESUME LAYOUT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def generate_resume_docx(
    data: ResumeLayoutInput,
    output_path: str,
) -> str:
    """Pure layout function — no LLM, no network, no I/O beyond the file write.

    Returns the absolute path to the generated ``.docx``.
    """
    doc = Document()

    # ── Page margins ──────────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin = _MARGIN
        section.bottom_margin = _MARGIN
        section.left_margin = _MARGIN
        section.right_margin = _MARGIN

    # ── HEADER ────────────────────────────────────────────────────────────
    name_para = doc.add_paragraph()
    name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_run = name_para.add_run(data.contact.name)
    _set_font(name_run, size=_NAME_SIZE, bold=True)

    contact_parts = [
        data.contact.email,
        data.contact.phone,
        data.contact.location,
        data.contact.linkedin,
        data.contact.github,
    ]
    contact_line = " | ".join(p for p in contact_parts if p)
    if contact_line:
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = cp.add_run(contact_line)
        _set_font(cr, size=_CONTACT_SIZE, color=_GRAY)

    # ── OBJECTIVE / SUMMARY (never truncated) ─────────────────────────────
    summary = (data.content.summary or "").strip()
    if summary:
        _add_section_heading(doc, "Objective")
        cleaned_summary = clean_text(summary)
        if cleaned_summary:
            _add_body_paragraph(doc, cleaned_summary)

    # ── HIGHLIGHTS ────────────────────────────────────────────────────────
    highlights = [h for h in data.content.highlights if h and h.strip()]
    if highlights:
        _add_section_heading(doc, "Highlights")
        for h in highlights:
            _add_bullet(doc, h)

    # ── Decide section order: Experience before Education (unless no exp) ─
    has_experience = bool(data.experience)

    if has_experience:
        _render_experience(doc, data)
        _render_projects(doc, data)
        _render_education(doc, data)
    else:
        _render_education(doc, data)
        _render_projects(doc, data)

    _render_certifications(doc, data)
    _render_activities(doc, data)

    # ── TECHNICAL SKILLS ──────────────────────────────────────────────────
    _render_skills(doc, data)

    # ── Write file ────────────────────────────────────────────────────────
    out = _ensure_output_dir(output_path)
    doc.save(out)
    return out


# ── Section renderers ─────────────────────────────────────────────────────────

def _render_experience(doc: Document, data: ResumeLayoutInput) -> None:
    entries = data.experience
    if not entries:
        return

    _add_section_heading(doc, "Experience")

    for entry in entries:
        # Header line: "Role – Company, Location | Mon. YYYY–Mon. YYYY"
        para = doc.add_paragraph()
        _set_paragraph_spacing(para, before=3, after=1, line_spacing=_LINE_SPACING)

        # Role (bold)
        role_text = entry.role or "Role"
        role_run = para.add_run(role_text)
        _set_font(role_run, bold=True)

        # Company, Location
        company_parts = [entry.company, entry.location]
        company_text = ", ".join(p for p in company_parts if p)
        if company_text:
            sep_run = para.add_run(" \u2013 ")  # en-dash
            _set_font(sep_run)
            co_run = para.add_run(company_text)
            _set_font(co_run)

        # Date range (italic)
        date_range = _format_date_range(entry.start_date, entry.end_date)
        if date_range:
            pipe_run = para.add_run(" | ")
            _set_font(pipe_run)
            date_run = para.add_run(date_range)
            _set_font(date_run, italic=True)

        # Bullets from description.
        bullets = _extract_bullets(entry.description)

        # Merge any tailored notes for this entry.
        extra = data.content.experience_notes.get(entry.id, [])
        bullets.extend(extra)

        for b in bullets:
            _add_bullet(doc, b)


def _render_projects(doc: Document, data: ResumeLayoutInput) -> None:
    # Filter to selected projects.
    used_ids = set(data.content.projects_used) if data.content.projects_used else None
    selected: List[ProjectEntry] = []
    for p in data.projects:
        if used_ids is None or p.id in used_ids:
            selected.append(p)
    if not selected:
        return

    _add_section_heading(doc, "Projects")

    for proj in selected:
        # Title line: "Title | Tech1, Tech2"
        para = doc.add_paragraph()
        _set_paragraph_spacing(para, before=3, after=1, line_spacing=_LINE_SPACING)

        title_run = para.add_run(proj.title)
        _set_font(title_run, bold=True)

        techs = ", ".join(t for t in proj.technologies if t)
        if techs:
            sep_run = para.add_run(" | ")
            _set_font(sep_run)
            tech_run = para.add_run(techs)
            _set_font(tech_run)

        # Links on the same line if present.
        links: List[str] = []
        if proj.github:
            links.append(f"GitHub: {proj.github}")
        if proj.deployment:
            links.append(f"Live Demo: {proj.deployment}")
        if links:
            link_run = para.add_run(" | " + " | ".join(links))
            _set_font(link_run, size=Pt(8), color=_GRAY)

        # Description bullets.
        bullets = _extract_bullets(proj.description)
        for b in bullets:
            _add_bullet(doc, b)


def _render_education(doc: Document, data: ResumeLayoutInput) -> None:
    entries = data.education
    if not entries:
        return

    degree_present = _has_degree(entries)

    # Filter out high-school when a degree exists.
    filtered = [
        e for e in entries
        if not (degree_present and _is_highschool(e))
    ]
    if not filtered:
        return

    # Sort most recent first (by end_date descending, then start_date).
    def _sort_key(e: EducationEntry) -> str:
        return e.end_date or e.start_date or ""
    filtered.sort(key=_sort_key, reverse=True)

    _add_section_heading(doc, "Education")

    for entry in filtered:
        # Line 1: Institution (bold)
        para = doc.add_paragraph()
        _set_paragraph_spacing(para, before=2, after=1, line_spacing=_LINE_SPACING)

        inst_run = para.add_run(entry.institution)
        _set_font(inst_run, bold=True)

        # Line 1 continued: "Degree in Field (CGPA x.x)"
        degree_parts: List[str] = []
        if entry.degree:
            deg = entry.degree
            if entry.field:
                deg += f" in {entry.field}"
            degree_parts.append(deg)
        if entry.grade:
            degree_parts.append(f"CGPA {entry.grade}")

        if degree_parts:
            sep_run = para.add_run(" \u2014 ")  # em-dash
            _set_font(sep_run)
            deg_run = para.add_run(" (".join(degree_parts[:1]) + (f" ({degree_parts[1]})" if len(degree_parts) > 1 else ""))
            _set_font(deg_run)

        # Location | YYYY–YYYY
        loc_date_parts: List[str] = []
        if entry.location:
            loc_date_parts.append(entry.location)
        date_range = _format_date_range(entry.start_date, entry.end_date)
        if date_range:
            loc_date_parts.append(date_range)
        if loc_date_parts:
            pipe_run = para.add_run(" | ")
            _set_font(pipe_run)
            ld_run = para.add_run(" | ".join(loc_date_parts))
            _set_font(ld_run, italic=True)


def _render_certifications(doc: Document, data: ResumeLayoutInput) -> None:
    items = [c.strip() for c in data.certifications if c and c.strip()]
    if not items:
        return

    _add_section_heading(doc, "Certifications")
    for cert in items:
        para = doc.add_paragraph()
        _set_paragraph_spacing(para, before=2, after=1, line_spacing=_LINE_SPACING)
        run = para.add_run(cert)
        _set_font(run)


def _render_activities(doc: Document, data: ResumeLayoutInput) -> None:
    items = [a.strip() for a in data.activities if a and a.strip()]
    if not items:
        return

    _add_section_heading(doc, "Activities")
    para = doc.add_paragraph()
    _set_paragraph_spacing(para, before=2, after=1, line_spacing=_LINE_SPACING)
    run = para.add_run(" | ".join(items))
    _set_font(run)


def _render_skills(doc: Document, data: ResumeLayoutInput) -> None:
    # Use pre-grouped skills from content contract if available.
    groups = data.content.skills_grouped
    if not groups:
        groups = normalize_skills(data.raw_skills)
    if not groups:
        return

    _add_section_heading(doc, "Technical Skills")

    for group_name, items in groups.items():
        if not items:
            continue
        para = doc.add_paragraph()
        _set_paragraph_spacing(para, line_spacing=_LINE_SPACING)

        label_run = para.add_run(f"{group_name}: ")
        _set_font(label_run, bold=True)

        skills_run = para.add_run(", ".join(items))
        _set_font(skills_run)


# ── Bullet extraction ─────────────────────────────────────────────────────────

def _extract_bullets(text: str) -> List[str]:
    """Split a description block into individual bullet strings."""
    if not text or not text.strip():
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


# ═══════════════════════════════════════════════════════════════════════════════
# COVER LETTER (untouched — kept as-is)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_cover_letter_docx(
    profile: Dict[str, Any],
    company_name: str,
    role_title: str,
    cover_letter_text: str,
    output_dir: str = _OUTPUT_DIR,
) -> str:
    doc = Document()

    for section in doc.sections:
        section.top_margin = Pt(54)
        section.bottom_margin = Pt(54)
        section.left_margin = Pt(72)
        section.right_margin = Pt(72)

    # Sender header
    name_p = doc.add_paragraph()
    name_p.add_run(profile.get("name", "Your Name")).bold = True
    contacts = [profile.get("email", ""), profile.get("phone", ""), profile.get("linkedin", "")]
    doc.add_paragraph("  |  ".join(c for c in contacts if c))
    doc.add_paragraph(datetime.now().strftime("%B %d, %Y"))
    doc.add_paragraph()

    # Addressee
    doc.add_paragraph(f"Hiring Manager\n{company_name}")
    doc.add_paragraph()

    # Subject line
    subj = doc.add_paragraph()
    subj.add_run(f"Re: Application for {role_title}").bold = True
    doc.add_paragraph()

    # Body paragraphs (split on double newlines)
    for para in cover_letter_text.strip().split("\n\n"):
        if para.strip():
            doc.add_paragraph(para.strip())

    # Closing
    doc.add_paragraph()
    doc.add_paragraph("Sincerely,")
    doc.add_paragraph()
    doc.add_paragraph(profile.get("name", ""))

    safe_company = company_name.replace(" ", "_")
    date_str = datetime.now().strftime("%Y%m%d")
    output_dir_path = Path(output_dir) if isinstance(output_dir, (str, os.PathLike)) else _OUTPUT_DIR
    if not output_dir_path.is_absolute():
        output_dir_path = _PROJECT_ROOT / output_dir_path
    output_dir_path.mkdir(parents=True, exist_ok=True)
    path = _ensure_output_dir(output_dir_path / f"cover_letter_{safe_company}_{date_str}.docx")
    doc.save(path)
    return path
