import json
import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from app.core.graph import agent_graph, tailoring_graph
from app.core.state import AgentState
from app.core.memory import init_db, update_job_status, log_step, sweep_stale_jobs, JOB_STATUSES
from app.core import jobs as job_store
from pydantic import BaseModel
import PyPDF2
import io
from typing import List

app = FastAPI(title="JobFit AI")

# Initialize DB on startup
@app.on_event("startup")
async def startup():
    init_db()
    sweep_stale_jobs()

# Helper to extract text from PDF
def extract_text_from_pdf(file_bytes):
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    return " ".join([page.extract_text() for page in reader.pages])

# The background worker
def run_agent_task(job_id: str, jd_text: str, resume_text: str):
    try:
        # Initial state
        initial_state = {
            "job_id": job_id,
            "jd_text": jd_text,
            "resume_text": resume_text,
            "company_name": None,
            "required_skills": [],
            "tech_stack": [],
            "findings": [],
            "iteration": 0,
            "max_iterations": 3,
            "tool_call_count": 0,
            "max_tool_calls": 10,
            "gap_analysis": None,
            "suggested_bullets": [],
            "final_report": None,
            "status": "researching"
        }

        # Run the LangGraph
        final_state = agent_graph.invoke(initial_state)
        
        # Save final report to DB
        update_job_status(job_id, "done", final_state.get("final_report", "No report generated"))
        
    except Exception as e:
        update_job_status(job_id, "failed", f"Error: {str(e)}")

# API Endpoint
@app.post("/analyze")
async def analyze_job(
    background_tasks: BackgroundTasks,
    jd: str = Form(...),
    resume: UploadFile = File(...)
):
    job_id = str(uuid.uuid4())
    
    # Read resume
    resume_bytes = await resume.read()
    resume_text = extract_text_from_pdf(resume_bytes)
    
    # Start background task
    update_job_status(job_id, "processing")
    background_tasks.add_task(run_agent_task, job_id, jd, resume_text)
    
    return {"job_id": job_id, "status": "processing", "message": "Your analysis is running in the background."}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    from app.core.memory import get_db
    with get_db() as conn:
        row = conn.execute("SELECT status, final_report FROM job_results WHERE job_id = ?", (job_id,)).fetchone()
        if row:
            return {"job_id": job_id, "status": row["status"], "report": row["final_report"]}
        return {"job_id": job_id, "status": "not_found"}


# =============================================================================
# SETUP ENDPOINTS
# =============================================================================

@app.post("/setup/profile")
async def setup_profile(resume: UploadFile = File(...)):
    """Parse an uploaded resume PDF and store the structured profile."""
    from app.core.profile_parser import extract_profile, parse_projects_text
    from app.core.profile_store import save_profile, save_projects
    from app.core.markdown_exporter import export_profile_to_markdown

    resume_bytes = await resume.read()
    try:
        resume_text = extract_text_from_pdf(resume_bytes)
    except PyPDF2.errors.PdfReadError:
        raise HTTPException(status_code=422, detail="Unable to read PDF file")
    profile = extract_profile(resume_text)

    # Extract structured projects from the raw "projects" section text
    raw_projects_text = profile.get("projects", "")
    if raw_projects_text.strip():
        structured_projects = parse_projects_text(raw_projects_text)
        if structured_projects:
            profile["project_list"] = structured_projects
            save_projects(structured_projects)

    save_profile(profile)
    md_files = export_profile_to_markdown(profile, llm_cfg={})

    return {
        "message": "Profile set up successfully.",
        "name": profile.get("name", ""),
        "skills_found": len(profile.get("skills", [])),
        "projects_found": len(profile.get("project_list", [])),
        "sections_parsed": [k for k in ("education", "experience", "certifications", "projects", "activities") if profile.get(k)],
        "markdown_files": md_files,
    }


def validate_project_entries(project_list: list) -> None:
    """Validate project entries on save, rejecting missing titles, short descriptions, or cross-contaminated text."""
    for idx, p in enumerate(project_list):
        if not isinstance(p, dict):
            raise HTTPException(status_code=422, detail=f"Project entry at index {idx} must be a dictionary.")
        title = (p.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail=f"Project at index {idx} is missing a title.")
        desc = (p.get("description") or "").strip()
        if len(desc) < 30:
            raise HTTPException(
                status_code=422,
                detail=f"Project '{title}' has a suspicious description (under 30 characters).",
            )
        title_lower = title.lower()
        desc_lower = desc.lower()
        tech_text = " ".join(str(t).lower() for t in p.get("technologies", []))

        # Check for cross-contamination signatures:
        suspicious_cross_indicators = [
            (["portfolio", "cms", "blog platform"], ["demand forecasting", "newsvendor", "safety stock", "sku-level", "prophet"]),
            (["churn", "customer retention"], ["language server protocol", "lsp", "compiler", "symbol index"]),
        ]
        for title_keywords, forbidden_desc_keywords in suspicious_cross_indicators:
            if any(tk in title_lower for tk in title_keywords):
                mismatched = [fk for fk in forbidden_desc_keywords if fk in desc_lower and fk not in tech_text]
                if mismatched:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Project '{title}' has a suspicious description containing mismatched keywords "
                            f"({', '.join(mismatched)}) that do not appear in the project title or technologies."
                        ),
                    )


@app.post("/setup/projects")
async def setup_projects(
    projects: str = Form(default=""),
    raw_text: str = Form(default=""),
    file: UploadFile = File(default=None),
):
    """Accept projects via: JSON array | pasted text | PDF/DOCX upload."""
    from app.core.profile_parser import parse_projects_text
    from app.core.profile_store import save_projects
    from app.core.markdown_exporter import export_projects_to_json

    project_list: list = []

    # --- Path 1: structured JSON array (legacy / manual form) ---
    if projects.strip():
        try:
            parsed = json.loads(projects)
            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON array")
            project_list = parsed
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid projects JSON: {exc}")

    # --- Path 2: PDF or DOCX file upload ---
    elif file and file.filename:
        file_bytes = await file.read()
        fname = (file.filename or "").lower()
        if fname.endswith(".pdf"):
            text = extract_text_from_pdf(file_bytes)
        elif fname.endswith(".docx"):
            try:
                import docx
                import io
                doc = docx.Document(io.BytesIO(file_bytes))
                text = "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                raise HTTPException(status_code=422, detail="python-docx not installed. Paste text instead.")
        else:
            raise HTTPException(status_code=422, detail="Only PDF or DOCX files are supported.")
        project_list = parse_projects_text(text)

    # --- Path 3: pasted raw text ---
    elif raw_text.strip():
        project_list = parse_projects_text(raw_text)

    else:
        raise HTTPException(status_code=422, detail="Provide a file, raw_text, or projects JSON.")

    if not project_list:
        raise HTTPException(status_code=422, detail="No projects could be parsed from the provided input.")

    validate_project_entries(project_list)

    # Keep the full parsed list in storage and export it as-is.
    save_projects(project_list)
    json_path = export_projects_to_json(project_list)

    return {
        "message": f"{len(project_list)} project(s) saved.",
        "projects_found": len(project_list),
        "titles": [p.get("title", "") for p in project_list],
        "json_file": json_path,
    }


@app.get("/setup/status")
async def setup_status():
    from app.core.profile_store import profile_exists, load_profile, load_projects
    if not profile_exists():
        return {"ready": False, "message": "Profile not set up yet."}
    profile = load_profile() or {}
    projects = load_projects()
    return {
        "ready": True,
        "name": profile.get("name", ""),
        "skills": profile.get("skills", []),
        "projects_count": len(projects),
        "sections": [k for k in ("education", "experience", "certifications", "projects", "activities") if profile.get(k)],
    }


# =============================================================================
# CAREER PROFILE ENDPOINTS
# =============================================================================

_PROFILE_TEXT_FIELDS = (
    "name", "email", "phone", "linkedin", "github", "location", "summary",
)


class SkillGroup(BaseModel):
    category: str = "General"
    skills: list[str] = []


class ProjectItem(BaseModel):
    title: str
    description: str = ""
    github: str = ""
    deployment: str = ""
    technologies: list[str] | str = []


class ProfileUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    location: str | None = None
    summary: str | None = None
    skills: list[str] | None = None
    skill_groups: list[SkillGroup] | None = None
    experience_items: list[dict[str, str | None]] | None = None
    education_items: list[dict[str, str | None]] | None = None
    certifications_items: list[dict[str, str | None]] | None = None
    activities_items: list[dict[str, str | None]] | None = None
    projects: list[ProjectItem] | None = None


@app.get("/profile")
async def get_profile():
    from app.core.profile_store import load_profile, load_projects
    from app.core.profile_sections import sections_view
    profile = load_profile() or {}
    out = {f: profile.get(f, "") or "" for f in _PROFILE_TEXT_FIELDS}
    out["skills"] = profile.get("skills", []) or []
    out.update(sections_view(profile))
    out["projects"] = load_projects()
    return out


@app.put("/profile")
async def update_profile(body: ProfileUpdate):
    """Partial update of the career profile; omitted fields are left unchanged."""
    from app.core.profile_store import load_profile, save_profile, save_projects
    from app.core.profile_sections import apply_sections, clean_skill_groups, flatten_skills
    changes = body.model_dump(exclude_unset=True)
    projects = changes.pop("projects", None)

    if "skills" in changes and "skill_groups" not in changes:
        changes["skill_groups"] = [{"category": "General", "skills": changes["skills"] or []}]
    changes.pop("skills", None)

    profile = load_profile() or {}
    section_keys = ("skill_groups", "experience_items", "education_items",
                    "certifications_items", "activities_items")
    section_changes = {k: changes.pop(k) for k in section_keys if k in changes}
    profile.update(changes)
    apply_sections(profile, section_changes)

    if projects is not None:
        if any(not (p.get("title") or "").strip() for p in projects):
            raise HTTPException(status_code=422, detail="Every project needs a title.")
        save_projects(projects)
        profile["project_list"] = projects
    save_profile(profile)
    return await get_profile()


# =============================================================================
# GENERATE ENDPOINTS
# =============================================================================

class GenerateForm(BaseModel):
    jd: str = ""
    company: str = ""
    role: str = ""
    job_id: str = ""
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""


def resolve_generation_inputs(job: dict | None, form: GenerateForm | dict) -> dict:
    """Reconcile tracked-job stored data with form submission overrides."""
    if isinstance(form, dict):
        f_company = (form.get("company") or "").strip()
        f_role = (form.get("role") or "").strip()
        f_jd = (form.get("jd") or "").strip()
    else:
        f_company = (getattr(form, "company", None) or "").strip()
        f_role = (getattr(form, "role", None) or "").strip()
        f_jd = (getattr(form, "jd", None) or "").strip()

    if not job:
        if not f_company or not f_role or not f_jd:
            raise ValueError("Company, role, and job description are all required.")
        return {
            "company": f_company,
            "role": f_role,
            "jd_text": f_jd,
            "overrides": {},
            "jd_source": "form",
        }

    base_company = (job.get("company") or "").strip()
    base_role = (job.get("role") or "").strip()
    base_jd = (job.get("jd_text") or "").strip()

    overrides: dict[str, str] = {}

    if f_company and f_company != base_company:
        resolved_company = f_company
        overrides["company"] = f_company
    else:
        resolved_company = base_company

    if f_role and f_role != base_role:
        resolved_role = f_role
        overrides["role"] = f_role
    else:
        resolved_role = base_role

    if f_jd and f_jd != base_jd:
        resolved_jd = f_jd
        overrides["jd_text"] = f_jd
        jd_source = "form_override"
    else:
        resolved_jd = base_jd
        jd_source = "stored_value"

    if not resolved_company or not resolved_role or not resolved_jd:
        raise ValueError("Company, role, and job description are all required.")

    return {
        "company": resolved_company,
        "role": resolved_role,
        "jd_text": resolved_jd,
        "overrides": overrides,
        "jd_source": jd_source,
    }


def run_tailoring_task(
    job_id: str,
    jd_text: str,
    company_name: str,
    role_title: str,
    llm_config: dict | None = None,
    tracker_job_id: str | None = None,
    overrides: dict | None = None,
    jd_source: str | None = None,
):
    from app.core.profile_store import profile_exists
    try:
        if not profile_exists():
            update_job_status(job_id, "failed", "Profile not set up. Please complete setup first.")
            return

        initial_state = {
            "job_id": job_id,
            "jd_text": jd_text,
            "company_name": company_name,
            "role_title": role_title,
            "user_profile": {},
            "company_findings": [],
            "tailored_bullets": [],
            "cover_letter_text": None,
            "gap_analysis": None,
            "resume_docx_path": None,
            "cover_letter_docx_path": None,
            "llm_config": llm_config or {},
            "iteration": 0,
            "max_iterations": 2,
            "status": "running",
        }
        final_state = tailoring_graph.invoke(initial_state)
        result = json.dumps({
            "type": "tailoring",
            "resume": final_state.get("resume_docx_path"),
            "cover_letter": final_state.get("cover_letter_docx_path"),
            "gaps": final_state.get("gap_analysis", ""),
        })
        update_job_status(job_id, "done", result)
        if tracker_job_id:
            if overrides:
                job_store.update_job(tracker_job_id, overrides)
            job_store.attach_generation(
                tracker_job_id, job_id,
                final_state.get("resume_docx_path"),
                final_state.get("cover_letter_docx_path"),
                final_state.get("gap_analysis", ""),
                jd_source=jd_source,
            )
    except Exception as e:
        update_job_status(job_id, "failed", str(e))


@app.post("/generate")
async def generate_documents(
    background_tasks: BackgroundTasks,
    jd: str = Form(default=""),
    company: str = Form(default=""),
    role: str = Form(default=""),
    llm_provider: str = Form(default=""),
    llm_api_key: str = Form(default=""),
    llm_model: str = Form(default=""),
    llm_base_url: str = Form(default=""),
    job_id: str = Form(default=""),
):
    from app.core.profile_store import profile_exists
    if not profile_exists():
        raise HTTPException(status_code=400, detail="Profile not set up. Call /setup/profile first.")
    tracker_job_id = job_id.strip() or None
    stored_job = None
    if tracker_job_id:
        record = job_store.get_job(tracker_job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Tracked job not found.")
        stored_job = record["job"]

    form_obj = GenerateForm(
        jd=jd,
        company=company,
        role=role,
        job_id=job_id,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )
    try:
        resolved = resolve_generation_inputs(stored_job, form_obj)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    llm_config = {
        "provider":  llm_provider  or None,
        "api_key":   llm_api_key   or None,
        "model":     llm_model     or None,
        "base_url":  llm_base_url  or None,
    }

    run_id = str(uuid.uuid4())
    update_job_status(run_id, "processing", tracker_job_id=tracker_job_id)
    background_tasks.add_task(
        run_tailoring_task,
        run_id,
        resolved["jd_text"],
        resolved["company"],
        resolved["role"],
        llm_config,
        tracker_job_id,
        resolved["overrides"],
        resolved["jd_source"],
    )
    return {"job_id": run_id, "status": "processing", "message": "Generating tailored resume and cover letter."}


@app.get("/download/{doc_type}/{job_id}")
async def download_document(doc_type: str, job_id: str):
    """Serve a generated DOCX file. doc_type is 'resume' or 'cover_letter'."""
    if doc_type not in ("resume", "cover_letter"):
        raise HTTPException(status_code=400, detail="doc_type must be 'resume' or 'cover_letter'")

    from app.core.memory import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT status, final_report FROM job_results WHERE job_id = ?", (job_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    if row["status"] != "done":
        raise HTTPException(status_code=400, detail=f"Job status is '{row['status']}', not done yet.")

    try:
        data = json.loads(row["final_report"])
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Could not parse job result.")

    if data.get("type") != "tailoring":
        raise HTTPException(status_code=400, detail="Job is not a tailoring job.")

    file_path = data.get(doc_type)
    file_path_obj = Path(file_path) if file_path else None
    if file_path_obj is None or not file_path_obj.is_absolute():
        file_path_obj = Path(__file__).resolve().parents[1] / file_path_obj if file_path_obj else None
    if not file_path_obj or not file_path_obj.exists():
        raise HTTPException(status_code=404, detail=f"Generated file not found: {file_path}")

    filename = file_path_obj.name
    return FileResponse(
        path=str(file_path_obj),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# =============================================================================
# JOB TRACKER ENDPOINTS
# =============================================================================

class JobCreate(BaseModel):
    company: str
    role: str
    jd_text: str | None = None
    app_url: str | None = None
    location: str | None = None
    salary_range: str | None = None
    deadline: str | None = None
    status: str = "saved"
    notes: str | None = None


class JobUpdate(BaseModel):
    company: str | None = None
    role: str | None = None
    jd_text: str | None = None
    app_url: str | None = None
    location: str | None = None
    salary_range: str | None = None
    deadline: str | None = None
    status: str | None = None
    notes: str | None = None


@app.post("/jobs", status_code=201)
async def create_job(body: JobCreate):
    if not body.company.strip() or not body.role.strip():
        raise HTTPException(status_code=422, detail="company and role are required")
    try:
        return job_store.create_job(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/jobs")
async def list_jobs(status: str | None = None):
    if status and status not in JOB_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status '{status}'")
    return job_store.list_jobs(status)


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    data = job_store.get_job(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found.")
    return data


@app.patch("/jobs/{job_id}")
async def update_job(job_id: str, body: JobUpdate):
    try:
        job = job_store.update_job(job_id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str):
    if not job_store.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found.")


@app.get("/jobs/{job_id}/artifacts/{kind}")
async def download_job_artifact(job_id: str, kind: str):
    if kind not in ("resume", "cover_letter"):
        raise HTTPException(status_code=400, detail="kind must be 'resume' or 'cover_letter'")
    rel = job_store.get_artifact_path(job_id, kind)
    path = job_store.resolve_path(rel) if rel else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
