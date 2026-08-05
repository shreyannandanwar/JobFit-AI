import logging
import re
from typing import Any, Dict

from app.core.memory import log_step
from app.core.plagiarism_reducer import reduce_plagiarism_risk
from app.core.state import AgentState
from app.core.tools import extract_relevant_excerpts, search_web

logger = logging.getLogger(__name__)


def _get_project_store_path() -> str:
    from pathlib import Path
    return str((Path(__file__).resolve().parents[1] / "output" / "profile" / "projects.json"))


def _load_relevant_projects(profile: Dict[str, Any], jd_text: str, role_title: str) -> list[Dict[str, Any]]:
    from pathlib import Path
    import json

    projects = profile.get("project_list") or []
    if not projects:
        project_store = Path(_get_project_store_path())
        if project_store.exists():
            try:
                projects = json.loads(project_store.read_text(encoding="utf-8"))
            except Exception:
                projects = []

    if not projects:
        return []

    def _normalize(token: str) -> str:
        token = re.sub(r"[^a-z0-9]+", "", token.lower())
        if token.endswith("ing") and len(token) > 4:
            token = token[:-3]
        elif token.endswith("s") and len(token) > 3:
            token = token[:-1]
        elif token.endswith("ed") and len(token) > 4:
            token = token[:-2]
        return token

    jd_terms = {_normalize(token) for token in re.split(r"[^a-z0-9]+", f"{role_title} {jd_text}") if token}
    jd_terms = {term for term in jd_terms if len(term) > 2}

    scored = []
    for project in projects:
        title = str(project.get("title", "")).lower()
        description = str(project.get("description", "")).lower()
        technologies = " ".join(project.get("technologies", [])).lower()
        content = f"{title} {description} {technologies}"
        content_terms = {_normalize(token) for token in re.split(r"[^a-z0-9]+", content) if token}
        overlap = sum(1 for term in jd_terms if term and term in content_terms)
        title_overlap = sum(3 for term in jd_terms if term and term in {_normalize(token) for token in re.split(r"[^a-z0-9]+", title) if token})
        tech_bonus = sum(2 for term in ["python", "xgboost", "prophet", "ml", "api", "forecast", "deploy", "backend", "data"] if term in content)
        scored.append((overlap * 2 + title_overlap + tech_bonus, project))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [project for _, project in scored[:2]]
    return selected


def _extract_company_name(jd_text: str) -> str:
    text = jd_text.strip()
    known_skills = {
        "python",
        "aws",
        "docker",
        "kubernetes",
        "react",
        "javascript",
        "sql",
        "java",
        "api",
        "streamlit",
        "machine",
        "learning",
    }

    patterns = [
        r"company\s*[:\-]\s*([A-Z][A-Za-z0-9&.\- ]+)",
        r"\b(?:at|for)\s+([A-Z][A-Za-z0-9&.\-]+(?:\s+(?:Corp|Corporation|Inc|LLC|Company|Labs|Technologies|Systems|Solutions|Group|Co\.?))?)",
        r"\b(?:we are hiring|hiring|join)\s+(?:a|an|the)?\s*([A-Z][A-Za-z0-9&.\-]+(?:\s+(?:Corp|Corporation|Inc|LLC|Company|Labs|Technologies|Systems|Solutions|Group|Co\.?))?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        candidate = match.group(1).strip()
        tokens = [token.lower() for token in re.split(r"\s+", candidate) if token]
        if not candidate:
            continue
        if any(token in known_skills for token in tokens):
            continue
        return candidate

    return "Unknown Company"


def _extract_skills(jd_text: str, resume_text: str) -> list[str]:
    candidate_skills = [
        "python",
        "aws",
        "docker",
        "kubernetes",
        "react",
        "javascript",
        "sql",
        "java",
        "machine learning",
        "api",
        "streamlit",
    ]
    text = f"{jd_text} {resume_text}".lower()
    matched = [skill for skill in candidate_skills if skill in text]
    return matched[:5] or ["python", "aws", "docker"]


# --- Node 1: Planner ---
def planner_node(state: AgentState) -> Dict[str, Any]:
    job_id = state.get("job_id", "unknown")
    jd_text = state.get("jd_text", "")
    resume_text = state.get("resume_text", "")

    logger.info(f"[{job_id}] Planner: Extracting skills and company...")

    company_name = _extract_company_name(jd_text) or "Unknown Company"
    required_skills = _extract_skills(jd_text, resume_text)

    log_step(job_id, "planner", {
        "thought": f"Extracted company: {company_name}, Skills: {required_skills}",
        "tool": "heuristic_extract",
        "tool_output": f"company={company_name}; skills={required_skills}",
    })

    return {
        "company_name": company_name,
        "required_skills": required_skills,
        "current_sub_question": f"What technologies does {company_name} use?",
        "findings": [],
        "status": "researching",
    }


# --- Node 2: Researcher ---
def researcher_node(state: AgentState) -> Dict[str, Any]:
    job_id = state.get("job_id", "unknown")
    sub_q = state.get("current_sub_question", "tech stack")
    company = state.get("company_name", "the company")
    skills = state.get("required_skills", [])

    query = f"{company} {sub_q}"
    if skills:
        query = f"{company} {' '.join(skills[:2])} technology stack"

    logger.info(f"[{job_id}] Researcher: Searching for '{query}'...")
    log_step(job_id, "researcher", {"thought": f"Searching: {query}", "tool": "search", "tool_input": query})

    raw_results = search_web(query, max_results=5)
    excerpts = extract_relevant_excerpts(raw_results, context_keywords=skills, max_excerpts=3)

    new_findings = []
    for excerpt in excerpts:
        skill_match = any(skill.lower() in excerpt["excerpt"].lower() for skill in skills)
        final_conf = min(1.0, excerpt["confidence"] + (0.2 if skill_match else 0.0))

        finding = {
            "sub_question": sub_q,
            "source": excerpt.get("source", ""),
            "excerpt": excerpt.get("excerpt", ""),
            "confidence": final_conf,
        }
        new_findings.append(finding)

        log_step(job_id, "research_finding", {
            "sub_question": sub_q,
            "source": excerpt.get("source", ""),
            "tool_output": excerpt.get("excerpt", ""),
            "confidence": final_conf,
        })

    if not new_findings:
        new_findings.append(
            {
                "sub_question": sub_q,
                "source": "web_search_fallback",
                "excerpt": f"No specific data found for {company}; using local fallback evidence.",
                "confidence": 0.2,
            }
        )

    existing_findings = state.get("findings", [])
    existing_findings.extend(new_findings)

    return {
        "findings": existing_findings,
        "tech_stack": [
            f.get("excerpt", "")
            for f in new_findings
            if f.get("confidence", 0) > 0.5
        ],
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "iteration": state.get("iteration", 0) + 1,
        "status": "verifying",
    }


# --- Node 3: Verifier ---
def verifier_node(state: AgentState) -> Dict[str, Any]:
    job_id = state.get("job_id", "unknown")
    findings = state.get("findings", [])
    required_skills = state.get("required_skills", [])

    recent_findings = findings[-3:] if len(findings) >= 3 else findings
    avg_conf = sum(f.get("confidence", 0) for f in recent_findings) / max(1, len(recent_findings))

    logger.info(f"[{job_id}] Verifier: Avg confidence = {avg_conf:.2f}")
    log_step(job_id, "verifier", {"thought": f"Avg confidence: {avg_conf:.2f}", "confidence": avg_conf})

    skill_mentions = []
    for skill in required_skills:
        for finding in findings:
            if skill.lower() in finding.get("excerpt", "").lower():
                skill_mentions.append(skill)
                break

    evidence_score = len(skill_mentions) / max(1, len(required_skills))

    if avg_conf < 0.4 or evidence_score < 0.3:
        new_question = f"Specific evidence of {required_skills[0] if required_skills else 'technology'} used at {state.get('company_name', 'the company')}"
        return {
            "current_sub_question": new_question,
            "status": "researching",
            "iteration": state.get("iteration", 0) + 1,
        }

    return {
        "status": "reporting",
        "iteration": state.get("iteration", 0) + 1,
    }


# --- Node 4: Reporter ---
def reporter_node(state: AgentState) -> Dict[str, Any]:
    job_id = state.get("job_id", "unknown")
    findings = state.get("findings", [])
    required_skills = state.get("required_skills", [])
    resume_text = state.get("resume_text", "")

    tech_found = []
    for finding in findings:
        if finding.get("confidence", 0) > 0.5:
            for skill in required_skills:
                if skill.lower() in finding.get("excerpt", "").lower():
                    tech_found.append(skill)
    tech_found = list(dict.fromkeys(tech_found))

    logger.info(f"[{job_id}] Reporter: Generating gap analysis...")

    resume_lower = resume_text.lower()
    gaps = [skill for skill in required_skills if skill.lower() not in resume_lower]
    suggested_bullets = [
        f"Built production-ready solutions using {skill.title()} in a team environment."
        for skill in tech_found[:3]
    ] or [
        "Added measurable examples of modern software delivery practices and collaboration to the resume."
    ]

    report = f"""
## JobFit AI Report for {state.get('company_name', 'Company')}

### Overall Match Score: {max(0.1, 1.0 - (len(gaps) * 0.15)):.1f}

### 📊 Required Skills from JD
{', '.join(required_skills)}

### 🔍 Tech Stack Evidenced on Web
{', '.join(tech_found) if tech_found else '⚠️ No strong evidence found. Consider checking the company careers page directly.'}

### ⚠️ Gaps (Missing Skills)
{chr(10).join(['- ' + gap for gap in gaps]) if gaps else '✅ No critical gaps detected!'}

### ✍️ Suggested Resume Bullets to Add
{chr(10).join(['- ' + bullet for bullet in suggested_bullets])}

### 📚 Source Audit Trail (Top 3)
"""
    for finding in findings[:3]:
        report += f"\n* {finding.get('sub_question', 'Research')}: [{finding.get('source', 'source')}]({finding.get('source', '#')}) (Confidence: {finding.get('confidence', 0):.2f})"

    log_step(job_id, "reporter", {
        "thought": "Final report generated",
        "tool_output": report,
    })

    return {
        "final_report": report,
        "gap_analysis": ", ".join(gaps),
        "suggested_bullets": suggested_bullets,
        "status": "done",
    }


# =============================================================================
# TAILORING WORKFLOW NODES
# =============================================================================

def profile_loader_node(state: "TailoringState") -> Dict[str, Any]:  # type: ignore[name-defined]
    from app.core.profile_store import load_profile, load_projects
    profile = load_profile() or {}
    projects = load_projects()
    if projects:
        profile["project_list"] = projects
    return {"user_profile": profile}


def company_researcher_node(state: "TailoringState") -> Dict[str, Any]:  # type: ignore[name-defined]
    company = state.get("company_name", "")
    role = state.get("role_title", "")
    jd_text = state.get("jd_text", "")
    job_id = state.get("job_id", "unknown")

    skills = _extract_skills(jd_text, "")
    query = f"{company} {role} engineering culture tech stack"

    logger.info(f"[{job_id}] Company researcher: '{query}'")
    log_step(job_id, "company_researcher", {"tool": "search", "tool_input": query})

    raw = search_web(query, max_results=5)
    excerpts = extract_relevant_excerpts(raw, context_keywords=skills, max_excerpts=5)

    findings = [
        {
            "source": ex.get("source", ""),
            "excerpt": ex.get("excerpt", ""),
            "confidence": ex.get("confidence", 0.2),
        }
        for ex in excerpts
    ]
    if not findings:
        findings.append({
            "source": "fallback",
            "excerpt": f"No live results for {company}. Using JD as primary source.",
            "confidence": 0.2,
        })

    return {
        "company_findings": findings,
        "iteration": state.get("iteration", 0) + 1,
    }


def resume_tailor_node(state: "TailoringState") -> Dict[str, Any]:  # type: ignore[name-defined]
    profile = state.get("user_profile", {})
    jd_text = state.get("jd_text", "")
    company_name = state.get("company_name", "")
    role_title = state.get("role_title", "")
    job_id = state.get("job_id", "unknown")
    llm_cfg = state.get("llm_config") or {}

    required = _extract_skills(jd_text, "")
    resume_skills: list = profile.get("skills", [])
    missing = [s for s in required if s not in resume_skills]

    if llm_cfg.get("provider"):
        from app.core.llm import llm_chat
        projects_text = ""
        all_projects = profile.get("project_list", [])
        for p in all_projects:
            title = p.get('title', '')
            description = p.get('description', '')
            techs = ', '.join(p.get('technologies', []))
            projects_text += f"  - {title}: {description} ({techs})\n"
        prompt = (
            f"Job Description:\n{jd_text}\n\n"
            f"Company: {company_name}\nRole: {role_title}\n\n"
            f"Candidate Profile:\n"
            f"  Name: {profile.get('name', '')}\n"
            f"  Skills: {', '.join(resume_skills)}\n"
            f"  Education: {profile.get('education', '')[:300]}\n"
            f"  Experience: {profile.get('experience', '')[:500]}\n"
            f"  Projects:\n{projects_text}\n\n"
            "Write 6-8 strong resume bullet points tailored to this role. "
            "Each bullet must start with an action verb, include a metric or outcome where possible, "
            "and highlight skills from the job description. Output only the bullet list, one per line, "
            "prefixed with '• '."
        )
        raw = llm_chat(
            [{"role": "system", "content": "You are an expert resume writer."},
             {"role": "user",   "content": prompt}],
            llm_cfg,
        )
        bullets = [line.lstrip("•- ").strip() for line in raw.splitlines() if line.strip()]
    else:
        matched = [s for s in required if s in resume_skills]
        name = profile.get("name", "the applicant")
        bullets = [
            f"{name} is applying for the {role_title} role at {company_name}, "
            f"bringing proven expertise in {', '.join(matched[:3]) if matched else 'software engineering'}.",
        ]
        for skill in matched[:4]:
            bullets.append(
                f"Hands-on experience with {skill}, applied to deliver scalable and maintainable solutions."
            )

    log_step(job_id, "resume_tailor", {"thought": f"missing={missing}, llm={bool(llm_cfg.get('provider'))}"})
    return {"tailored_bullets": bullets, "gap_analysis": ", ".join(missing)}


def cover_letter_node(state: "TailoringState") -> Dict[str, Any]:  # type: ignore[name-defined]
    profile = state.get("user_profile", {})
    company_name = state.get("company_name", "")
    role_title = state.get("role_title", "")
    jd_text = state.get("jd_text", "")
    job_id = state.get("job_id", "unknown")
    llm_cfg = state.get("llm_config") or {}

    name = profile.get("name", "I")
    skills: list = profile.get("skills", [])
    experience = profile.get("experience", "").strip()
    findings = state.get("company_findings", [])
    cover_letter_text = ""

    if llm_cfg.get("provider"):
        from app.core.llm import llm_chat
        prompt = (
            f"Write a professional, plagiarism-free cover letter for:\n"
            f"  Applicant: {name}\n"
            f"  Role: {role_title}\n"
            f"  Company: {company_name}\n"
            f"  Skills: {', '.join(skills[:8])}\n"
            f"  Experience summary: {experience[:400]}\n"
            f"  Job Description excerpt: {jd_text[:600]}\n\n"
            "Requirements: 3-4 short paragraphs, no clichés, specific to the company and role, "
            "under 380 words. Output only the letter body — no subject line or signature."
        )
        cover_letter_text = llm_chat(
            [{"role": "system", "content": "You are an expert cover letter writer. Write original, human-sounding cover letters."},
             {"role": "user",   "content": prompt}],
            llm_cfg,
        )

    if not cover_letter_text or not cover_letter_text.strip():
        cover_letter_text = ""
    elif len(cover_letter_text.strip().split()) < 25:
        cover_letter_text = ""

    if not cover_letter_text or not cover_letter_text.strip():
        relevant_projects = _load_relevant_projects(profile, jd_text, role_title)
        project_mentions = []
        for project in relevant_projects:
            title = str(project.get("title", "")).strip()
            description = str(project.get("description", "")).strip()
            if title:
                summary = description if len(description) <= 140 else description[:137].rstrip() + "..."
                project_mentions.append(f"{title}: {summary}")

        skills_str = ", ".join(skills[:5]) if skills else "a broad set of engineering disciplines"
        opening = (
            f"I am writing to express my genuine interest in the {role_title} position at {company_name}. "
            f"With hands-on experience across {skills_str}, I have spent my career building systems "
            "that are both technically sound and directly aligned with real business outcomes."
        )
        exp_sentence = ""
        if experience:
            first_line = next((l for l in experience.splitlines() if l.strip()), "")
            if first_line:
                exp_sentence = (
                    f"Most recently, {first_line.lower().rstrip('.')}. "
                    "This background has sharpened my ability to move quickly while maintaining quality."
                )
        project_para = ""
        if project_mentions:
            project_para = (
                "Across my recent work, I have applied these strengths in projects such as "
                + "; ".join(project_mentions[:2])
                + ". These experiences strengthen my ability to deliver practical, production-focused solutions."
            )
        company_para = (
            f"What draws me to {company_name} specifically is the calibre of the engineering challenges "
            "and the emphasis on building with both rigour and velocity. "
        )
        if findings and findings[0].get("confidence", 0) >= 0.4:
            company_para += (
                "Based on my research into your technical direction and culture, "
                "I am confident that my experience maps closely to what your team is building."
            )
        else:
            company_para += (
                "I would welcome the opportunity to learn more about your roadmap "
                "and discuss how my background can contribute to it."
            )
        closing = (
            "I thrive in collaborative environments where engineers are expected to take ownership, "
            "think across the stack, and ship with confidence. "
            f"I would be glad to discuss how I can contribute to {company_name}'s mission. "
            "Thank you for your time and consideration."
        )
        cover_letter_text = "\n\n".join(filter(None, [opening, exp_sentence, project_para, company_para, closing]))
        cover_letter_text = reduce_plagiarism_risk(
            cover_letter_text,
            context=f"{company_name} for the {role_title} role",
        )

    log_step(job_id, "cover_letter", {"thought": f"Cover letter drafted, llm={bool(llm_cfg.get('provider'))}"})
    return {"cover_letter_text": cover_letter_text}


def docx_export_node(state: "TailoringState") -> Dict[str, Any]:  # type: ignore[name-defined]
    from app.core.docx_generator import generate_cover_letter_docx, generate_resume_docx

    profile = state.get("user_profile", {})
    company_name = state.get("company_name", "Company")
    role_title = state.get("role_title", "Role")
    jd_text = state.get("jd_text", "")
    bullets = state.get("tailored_bullets", [])
    cover_letter_text = state.get("cover_letter_text", "")
    job_id = state.get("job_id", "unknown")

    profile = dict(profile)
    profile["jd_text"] = jd_text

    resume_path = generate_resume_docx(profile, bullets, company_name, role_title)
    cover_path = generate_cover_letter_docx(profile, company_name, role_title, cover_letter_text)

    logger.info(f"[{job_id}] DOCX exported: {resume_path}, {cover_path}")
    return {
        "resume_docx_path": resume_path,
        "cover_letter_docx_path": cover_path,
        "status": "done",
    }
