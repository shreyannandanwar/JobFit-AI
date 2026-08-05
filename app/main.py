import json
import uuid
import asyncio
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from app.core.graph import agent_graph, tailoring_graph
from app.core.state import AgentState
from app.core.memory import init_db, update_job_status, log_step
import PyPDF2
import io
from typing import List

app = FastAPI(title="JobFit AI")

# Initialize DB on startup
@app.on_event("startup")
async def startup():
    init_db()

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
    resume_text = extract_text_from_pdf(resume_bytes)
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
# GENERATE ENDPOINTS
# =============================================================================

def run_tailoring_task(
    job_id: str,
    jd_text: str,
    company_name: str,
    role_title: str,
    llm_config: dict | None = None,
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
    except Exception as e:
        update_job_status(job_id, "failed", str(e))


@app.post("/generate")
async def generate_documents(
    background_tasks: BackgroundTasks,
    jd: str = Form(...),
    company: str = Form(...),
    role: str = Form(...),
    llm_provider: str = Form(default=""),
    llm_api_key: str = Form(default=""),
    llm_model: str = Form(default=""),
    llm_base_url: str = Form(default=""),
):
    from app.core.profile_store import profile_exists
    if not profile_exists():
        raise HTTPException(status_code=400, detail="Profile not set up. Call /setup/profile first.")

    llm_config = {
        "provider":  llm_provider  or None,
        "api_key":   llm_api_key   or None,
        "model":     llm_model     or None,
        "base_url":  llm_base_url  or None,
    }

    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_tailoring_task, job_id, jd, company, role, llm_config)
    return {"job_id": job_id, "status": "processing", "message": "Generating tailored resume and cover letter."}


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