import json
import os
import time

import requests
import streamlit as st

st.set_page_config(page_title="JobFit AI", layout="wide", page_icon="🎯")


def _get_setting(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.environ.get(key, default)


API_URL = _get_setting("API_URL", "http://localhost:8000")


def _api(method: str, path: str, **kwargs):
    try:
        resp = getattr(requests, method)(f"{API_URL}{path}", timeout=10, **kwargs)
        return resp
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the backend. Make sure the FastAPI server is running on port 8000.")
        st.stop()


# --- Sidebar: profile status ---
with st.sidebar:
    st.title("🎯 JobFit AI")
    st.caption("Tailored resumes & cover letters in seconds.")
    st.divider()
    status_resp = _api("get", "/setup/status")
    profile_data = status_resp.json() if status_resp.ok else {}
    profile_ready = profile_data.get("ready", False)

    if profile_ready:
        st.success(f"✅ Profile ready")
        st.write(f"**Name:** {profile_data.get('name', '—')}")
        st.write(f"**Skills:** {', '.join(profile_data.get('skills', [])[:6]) or '—'}")
        st.write(f"**Projects:** {profile_data.get('projects_count', 0)}")
        st.write(f"**Sections:** {', '.join(profile_data.get('sections', []))}")
    else:
        st.warning("⚠️ Profile not set up yet.\nComplete the Setup tab first.")

    st.divider()
    st.subheader("🤖 LLM Provider")

    _PROVIDERS = {
        "openrouter":    "OpenRouter (cloud, many models)",
        "openai":        "OpenAI (direct)",
        "ollama":        "Ollama (local)",
        "github_models": "GitHub Models",
    }
    _OLLAMA_MODELS   = ["llama3", "llama3.1", "mistral", "phi3", "gemma2", "codellama"]
    _OR_MODELS       = ["openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-3-haiku",
                        "meta-llama/llama-3-8b-instruct", "google/gemma-2-9b-it",
                        "inclusionai/ling-3.0-flash:free"]
    _OAI_MODELS      = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    _GH_MODELS       = ["gpt-4o-mini", "gpt-4o", "Phi-3.5-mini-instruct", "Mistral-small"]

    provider_key = st.selectbox(
        "Provider",
        options=list(_PROVIDERS),
        format_func=lambda k: _PROVIDERS[k],
        key="llm_provider",
    )

    # Show relevant model picker + key field per provider
    if provider_key == "ollama":
        llm_model = st.selectbox("Model", _OLLAMA_MODELS, key="llm_model_ol")
        llm_api_key = ""
        llm_base_url = st.text_input("Ollama base URL", value="http://localhost:11434/v1", key="llm_url_ol")
    elif provider_key == "openrouter":
        llm_model = st.selectbox("Model", _OR_MODELS, key="llm_model_or")
        llm_api_key = st.text_input("OpenRouter API key", type="password",
                                    value=os.environ.get("OPENROUTER_API_KEY", ""), key="llm_key_or")
        llm_base_url = ""
    elif provider_key == "openai":
        llm_model = st.selectbox("Model", _OAI_MODELS, key="llm_model_oai")
        llm_api_key = st.text_input("OpenAI API key", type="password",
                                    value=os.environ.get("OPENAI_API_KEY", ""), key="llm_key_oai")
        llm_base_url = ""
    else:  # github_models
        llm_model = st.selectbox("Model", _GH_MODELS, key="llm_model_gh")
        llm_api_key = st.text_input("GitHub token (with Models access)", type="password",
                                    value=os.environ.get("GITHUB_TOKEN", ""), key="llm_key_gh")
        llm_base_url = ""

    # Persist resolved values so the generate tab can read them
    st.session_state["_llm_cfg"] = {
        "provider":  provider_key,
        "api_key":   llm_api_key,
        "model":     llm_model,
        "base_url":  llm_base_url,
    }

# --- Main tabs ---
tab_setup, tab_profile, tab_jobs, tab_generate = st.tabs(
    ["⚙️ Setup Profile", "👤 Career Profile", "📋 My Jobs", "🚀 Generate Documents"]
)

# =============================================================================
# TAB 1 – SETUP
# =============================================================================
with tab_setup:
    st.header("Step 1 – Upload Your Resume")
    st.caption("We extract your name, contact info, skills, education, experience, and more.")

    with st.form("resume_form"):
        resume_file = st.file_uploader("Upload Resume (PDF)", type=["pdf"])
        submit_resume = st.form_submit_button("📄 Parse & Save Profile")

    if submit_resume:
        if not resume_file:
            st.error("Please upload a PDF resume.")
        else:
            with st.spinner("Parsing your resume…"):
                resp = _api("post", "/setup/profile", files={"resume": resume_file})
            if resp.ok:
                data = resp.json()
                n_proj = data.get("projects_found", 0)
                proj_note = f" Also extracted **{n_proj} project(s)** from resume." if n_proj else ""
                st.success(
                    f"Profile saved for **{data['name']}**. "
                    f"Found **{data['skills_found']} skills** and sections: "
                    f"{', '.join(data['sections_parsed']) or 'none detected'}.{proj_note}"
                )
                st.write("**Markdown files created:**")
                for f in data.get("markdown_files", []):
                    st.code(f)
                st.rerun()
            else:
                st.error(f"Failed to parse resume: {resp.text}")

    st.divider()
    st.header("Step 2 – Add Your Projects (Optional)")
    st.caption(
        "Upload a PDF / DOCX containing all your projects, or paste the text directly. "
        "GitHub links, demo URLs, and tech stacks are extracted automatically."
    )

    proj_tab_upload, proj_tab_paste = st.tabs(["📎 Upload PDF / DOCX", "📋 Paste Text"])

    with proj_tab_upload:
        with st.form("project_upload_form"):
            proj_file = st.file_uploader("Project document (PDF or DOCX)", type=["pdf", "docx"])
            submit_proj_file = st.form_submit_button("🔍 Parse & Save Projects")

        if submit_proj_file:
            if not proj_file:
                st.error("Please upload a PDF or DOCX file.")
            else:
                with st.spinner("Parsing projects…"):
                    resp = _api("post", "/setup/projects", files={"file": proj_file})
                if resp.ok:
                    data = resp.json()
                    st.success(
                        f"Saved **{data['projects_found']} project(s)**: "
                        f"{', '.join(data.get('titles', []))}"
                    )
                    st.caption(f"Written to `{data.get('markdown_file', '')}`")
                    st.rerun()
                else:
                    st.error(f"Failed: {resp.text}")

    with proj_tab_paste:
        with st.form("project_paste_form", clear_on_submit=True):
            pasted = st.text_area(
                "Paste your projects here",
                height=300,
                placeholder=(
                    "## My Project\n"
                    "A brief description of what it does.\n"
                    "GitHub: https://github.com/you/repo\n"
                    "Demo: https://myapp.com\n"
                    "Tech: Python, FastAPI, React\n\n"
                    "## Another Project\n"
                    "..."
                ),
            )
            submit_paste = st.form_submit_button("🔍 Parse & Save Projects")

        if submit_paste:
            if not pasted.strip():
                st.error("Please paste some project text.")
            else:
                with st.spinner("Parsing projects…"):
                    resp = _api("post", "/setup/projects", data={"raw_text": pasted})
                if resp.ok:
                    data = resp.json()
                    st.success(
                        f"Saved **{data['projects_found']} project(s)**: "
                        f"{', '.join(data.get('titles', []))}"
                    )
                    st.caption(f"Written to `{data.get('markdown_file', '')}`")
                    st.rerun()
                else:
                    st.error(f"Failed: {resp.text}")

# =============================================================================
# TAB – CAREER PROFILE (single source of truth)
# =============================================================================
def _save_profile(changes: dict, reset_keys: tuple = ()) -> None:
    resp = _api("put", "/profile", json=changes)
    if resp.ok:
        for k in reset_keys:
            st.session_state.pop(k, None)
        st.success("Saved.")
        st.rerun()
    else:
        st.error(resp.json().get("detail", resp.text))


_ENTRY_SPECS = {
    "experience": {
        "title": lambda e: " at ".join(x for x in (e.get("role"), e.get("company")) if x) or "New experience",
        "noun": "experience",
        "fields": [("role", "Role / Title *", "text"), ("company", "Company", "text"),
                   ("location", "Location", "text"), ("start_date", "Start (e.g. Jun 2024)", "text"),
                   ("end_date", "End (or Present)", "text"),
                   ("description", "Responsibilities & achievements (one bullet per line)", "area")],
    },
    "education": {
        "title": lambda e: ", ".join(x for x in (e.get("degree"), e.get("institution")) if x) or "New education",
        "noun": "education",
        "fields": [("institution", "Institution *", "text"), ("degree", "Degree", "text"),
                   ("field", "Field of study", "text"), ("location", "Location", "text"),
                   ("start_date", "Start", "text"), ("end_date", "End / Expected", "text"),
                   ("grade", "Grade / CGPA", "text"),
                   ("description", "Coursework, honours, notes", "area")],
    },
    "certifications": {
        "title": lambda e: e.get("name") or "New certification",
        "noun": "certification",
        "fields": [("name", "Certification name *", "text"), ("issuer", "Issuing organization", "text"),
                   ("date", "Date earned", "text"), ("credential_url", "Credential URL", "text")],
    },
    "activities": {
        "title": lambda e: " — ".join(x for x in (e.get("title"), e.get("organization")) if x) or "New activity",
        "noun": "activity",
        "fields": [("title", "Title / Role *", "text"), ("organization", "Organization", "text"),
                   ("start_date", "Start", "text"), ("end_date", "End", "text"),
                   ("description", "Description", "area")],
    },
}


def _new_uid() -> int:
    st.session_state["_uid_counter"] = st.session_state.get("_uid_counter", 0) + 1
    return st.session_state["_uid_counter"]


def _entries_editor(section: str, items: list) -> None:
    spec = _ENTRY_SPECS[section]
    state_key = f"{section}_entries"
    if state_key not in st.session_state:
        st.session_state[state_key] = [{**it, "_uid": _new_uid()} for it in items]
    entries = st.session_state[state_key]

    if not entries:
        st.info(f"No {spec['noun']} entries yet. Add one below.")

    remove_uid = None
    for idx, e in enumerate(entries):
        uid = e["_uid"]
        with st.expander(f"{idx + 1}. {spec['title'](e)}", expanded=not e.get(spec["fields"][0][0])):
            cols = st.columns(2)
            short = [f for f in spec["fields"] if f[2] == "text"]
            for n, (field, label, _) in enumerate(short):
                e[field] = cols[n % 2].text_input(label, value=e.get(field, ""), key=f"{section}_{uid}_{field}")
            for field, label, _ in (f for f in spec["fields"] if f[2] == "area"):
                e[field] = st.text_area(label, value=e.get(field, ""), height=140, key=f"{section}_{uid}_{field}")
            if st.button("🗑️ Remove this entry", key=f"{section}_{uid}_rm"):
                remove_uid = uid

    if remove_uid is not None:
        st.session_state[state_key] = [e for e in entries if e["_uid"] != remove_uid]
        st.rerun()

    c1, c2, _ = st.columns([1, 1, 3])
    if c1.button(f"➕ Add {spec['noun']}", key=f"{section}_add"):
        entries.append({f: "" for f, _, _ in spec["fields"]} | {"_uid": _new_uid()})
        st.rerun()
    if c2.button("💾 Save", key=f"{section}_save", type="primary"):
        payload = [{k: v for k, v in e.items() if k != "_uid"} for e in entries]
        _save_profile({f"{section}_items": payload}, reset_keys=(state_key,))


with tab_profile:
    st.header("Career Profile")
    st.caption("Your reusable source of truth. Edits here feed every generated resume and cover letter.")
    _p_resp = _api("get", "/profile")
    prof = _p_resp.json() if _p_resp.ok else {}

    (sub_personal, sub_skills, sub_exp, sub_edu, sub_proj, sub_cert, sub_act) = st.tabs(
        ["Personal & Summary", "Skills", "Experience", "Education", "Projects",
         "Certifications (optional)", "Activities"]
    )

    with sub_personal:
        with st.form("profile_personal"):
            c1, c2 = st.columns(2)
            with c1:
                f_name = st.text_input("Name", value=prof.get("name", ""))
                f_email = st.text_input("Email", value=prof.get("email", ""))
                f_phone = st.text_input("Phone", value=prof.get("phone", ""))
            with c2:
                f_linkedin = st.text_input("LinkedIn", value=prof.get("linkedin", ""))
                f_github = st.text_input("GitHub", value=prof.get("github", ""))
                f_location = st.text_input("Location", value=prof.get("location", ""))
            f_summary = st.text_area("Summary", value=prof.get("summary", ""), height=150)
            if st.form_submit_button("💾 Save"):
                _save_profile({"name": f_name, "email": f_email, "phone": f_phone,
                               "linkedin": f_linkedin, "github": f_github,
                               "location": f_location, "summary": f_summary})

    with sub_skills:
        st.caption("Group skills by category (e.g. Languages, Frameworks, Tools). Separate skills with commas.")
        if "skill_group_entries" not in st.session_state:
            st.session_state["skill_group_entries"] = [
                {"category": g["category"], "skills": ", ".join(g["skills"]), "_uid": _new_uid()}
                for g in prof.get("skill_groups", [])
            ]
        groups = st.session_state["skill_group_entries"]
        if not groups:
            st.info("No skills yet. Add a category below.")
        rm_group = None
        for g in groups:
            uid = g["_uid"]
            c1, c2, c3 = st.columns([1, 3, 0.5])
            g["category"] = c1.text_input("Category", value=g["category"], key=f"sg_cat_{uid}")
            g["skills"] = c2.text_area("Skills", value=g["skills"], height=80, key=f"sg_sk_{uid}")
            if c3.button("🗑️", key=f"sg_rm_{uid}"):
                rm_group = uid
        if rm_group is not None:
            st.session_state["skill_group_entries"] = [g for g in groups if g["_uid"] != rm_group]
            st.rerun()
        b1, b2, _ = st.columns([1, 1, 3])
        if b1.button("➕ Add category", key="sg_add"):
            groups.append({"category": "", "skills": "", "_uid": _new_uid()})
            st.rerun()
        if b2.button("💾 Save", key="sg_save", type="primary"):
            payload = [{"category": g["category"],
                        "skills": [x for chunk in g["skills"].splitlines() for x in chunk.split(",")]}
                       for g in groups]
            _save_profile({"skill_groups": payload}, reset_keys=("skill_group_entries",))

    with sub_exp:
        _entries_editor("experience", prof.get("experience_items", []))
    with sub_edu:
        _entries_editor("education", prof.get("education_items", []))
    with sub_cert:
        _entries_editor("certifications", prof.get("certifications_items", []))
    with sub_act:
        _entries_editor("activities", prof.get("activities_items", []))

    with sub_proj:
        st.caption("Add, edit, or delete rows. Technologies are comma separated.")
        rows = []
        for pr in prof.get("projects", []):
            techs = pr.get("technologies", [])
            if isinstance(techs, list):
                techs = ", ".join(techs)
            rows.append({"title": pr.get("title", ""), "description": pr.get("description", ""),
                         "github": pr.get("github", ""), "deployment": pr.get("deployment", ""),
                         "technologies": techs if isinstance(techs, str) else ""})
        edited = st.data_editor(
            rows or [{"title": "", "description": "", "github": "", "deployment": "", "technologies": ""}],
            num_rows="dynamic", use_container_width=True, key="projects_editor",
        )
        if st.button("💾 Save projects"):
            out = []
            for r in edited:
                if not (r.get("title") or "").strip():
                    continue
                out.append({
                    "title": r["title"].strip(),
                    "description": r.get("description") or "",
                    "github": r.get("github") or "",
                    "deployment": r.get("deployment") or "",
                    "technologies": [t.strip() for t in (r.get("technologies") or "").split(",") if t.strip()],
                })
            _save_profile({"projects": out})

# =============================================================================
# TAB – MY JOBS
# =============================================================================
_STATUSES = ["saved", "preparing", "applied", "assessment", "interview", "offer",
             "rejected", "withdrawn", "archived"]
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _fetch_jobs() -> list:
    resp = _api("get", "/jobs")
    return resp.json() if resp.ok else []


with tab_jobs:
    st.header("My Jobs")

    with st.expander("➕ Add Job"):
        with st.form("add_job_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                new_company = st.text_input("Company *")
                new_role = st.text_input("Role *")
                new_url = st.text_input("Application URL")
                new_location = st.text_input("Location")
                new_has_deadline = st.checkbox("Has deadline")
                new_deadline = st.date_input("Deadline")
            with c2:
                new_jd = st.text_area("Job Description", height=250)
            add_submitted = st.form_submit_button("Add Job")
        if add_submitted:
            if not new_company.strip() or not new_role.strip():
                st.error("Company and role are required.")
            else:
                resp = _api("post", "/jobs", json={
                    "company": new_company.strip(), "role": new_role.strip(),
                    "jd_text": new_jd or None, "app_url": new_url or None,
                    "location": new_location or None,
                    "deadline": new_deadline.isoformat() if new_has_deadline else None,
                })
                if resp.ok:
                    st.session_state["selected_job_id"] = resp.json()["job_id"]
                    st.rerun()
                else:
                    st.error(resp.text)

    all_jobs = _fetch_jobs()
    if not all_jobs:
        st.info("No jobs yet. Add your first one above.")
    else:
        status_filter = st.selectbox("Filter by status", ["all"] + _STATUSES, key="jobs_filter")
        shown = [j for j in all_jobs if status_filter == "all" or j["status"] == status_filter]
        table = [{"Company": j["company"], "Role": j["role"], "Status": j["status"],
                  "Location": j["location"] or "", "Deadline": j["deadline"] or "",
                  "Added": (j["created_at"] or "")[:10]} for j in shown]
        event = st.dataframe(table, use_container_width=True, hide_index=True,
                             on_select="rerun", selection_mode="single-row", key="jobs_table")
        rows = event.selection.rows if event else []
        if rows:
            st.session_state["selected_job_id"] = shown[rows[0]]["job_id"]

    selected_id = st.session_state.get("selected_job_id")
    detail = _api("get", f"/jobs/{selected_id}") if selected_id else None
    if detail is not None and detail.ok:
        data = detail.json()
        job, artifacts, events = data["job"], data["artifacts"], data["events"]
        st.divider()
        st.subheader(f"{job['company']} — {job['role']}")

        col_s, col_i = st.columns([1, 2])
        with col_s:
            new_status = st.selectbox("Status", _STATUSES, index=_STATUSES.index(job["status"]),
                                      key=f"status_{selected_id}")
            if new_status != job["status"]:
                if _api("patch", f"/jobs/{selected_id}", json={"status": new_status}).ok:
                    st.rerun()
        with col_i:
            st.write(f"**Location:** {job['location'] or '—'}  |  **Deadline:** {job['deadline'] or '—'}")
            if job["app_url"]:
                st.write(f"[Application link]({job['app_url']})")

        with st.expander("Job Description"):
            st.write(job["jd_text"] or "_No job description saved._")

        notes = st.text_area("Notes", value=job["notes"] or "", key=f"notes_{selected_id}")
        if st.button("💾 Save notes", key=f"save_notes_{selected_id}"):
            if _api("patch", f"/jobs/{selected_id}", json={"notes": notes}).ok:
                st.success("Notes saved.")
                st.rerun()

        st.markdown("**Documents**")
        has_files = False
        for kind, label in (("resume", "📄 Resume (.docx)"), ("cover_letter", "✉️ Cover Letter (.docx)")):
            if any(a["kind"] == kind and a["file_path"] for a in artifacts):
                r = _api("get", f"/jobs/{selected_id}/artifacts/{kind}")
                if r.ok:
                    has_files = True
                    st.download_button(label, data=r.content, mime=_DOCX_MIME,
                                       file_name=f"{kind}_{job['company'].replace(' ', '_')}.docx",
                                       key=f"dl_{kind}_{selected_id}")
        if not has_files:
            st.caption("No generated documents yet. Use the Generate tab and link this job.")

        st.markdown("**Timeline**")
        for e in reversed(events):
            detail_txt = ""
            if e["detail"]:
                try:
                    d = json.loads(e["detail"])
                    detail_txt = f" — {d['from']} → {d['to']}" if "from" in d else ""
                except (json.JSONDecodeError, TypeError):
                    pass
            st.write(f"`{e['created_at'][:16]}` {e['event_type'].replace('_', ' ')}{detail_txt}")

        if st.button("🗑️ Delete job", key=f"del_{selected_id}"):
            if _api("delete", f"/jobs/{selected_id}").ok:
                st.session_state["selected_job_id"] = None
                st.rerun()

# =============================================================================
# TAB 3 – GENERATE
# =============================================================================
with tab_generate:
    if not profile_ready:
        st.warning("Complete the **Setup** tab first before generating documents.")
        st.stop()

    st.header("Generate Tailored Resume & Cover Letter")

    _jobs_for_link = _fetch_jobs()
    _job_by_id = {j["job_id"]: j for j in _jobs_for_link}
    link_job_id = st.selectbox(
        "Link to job (optional)",
        options=[""] + list(_job_by_id),
        format_func=lambda k: "— none (one-off) —" if not k else f"{_job_by_id[k]['company']} — {_job_by_id[k]['role']}",
        key="link_job_id",
    )
    _linked = _job_by_id.get(link_job_id)
    if _linked:
        st.caption("Loaded from tracked job — edit to override.")

    with st.form("generate_form"):
        col1, col2 = st.columns([1, 1])
        with col1:
            company = st.text_input("Company Name *", placeholder="e.g. Stripe",
                                    value=_linked["company"] if _linked else "",
                                    key=f"gen_company_{link_job_id}")
            role = st.text_input("Role Title *", placeholder="e.g. Senior Backend Engineer",
                                 value=_linked["role"] if _linked else "",
                                 key=f"gen_role_{link_job_id}")
        with col2:
            jd = st.text_area("Job Description *", height=220, placeholder="Paste the full job description here…",
                              value=(_linked["jd_text"] or "") if _linked else "",
                              key=f"gen_jd_{link_job_id}")
        submitted = st.form_submit_button("🚀 Generate Documents")

    if submitted:
        if not company or not role or not jd:
            st.error("Company, role, and job description are all required.")
        else:
            cfg = st.session_state.get("_llm_cfg", {})
            with st.spinner("Submitting to JobFit AI…"):
                resp = _api("post", "/generate", data={
                    "jd": jd, "company": company, "role": role,
                    "llm_provider": cfg.get("provider", ""),
                    "llm_api_key":  cfg.get("api_key", ""),
                    "llm_model":    cfg.get("model", ""),
                    "llm_base_url": cfg.get("base_url", ""),
                    "job_id": link_job_id,
                })

            if not resp.ok:
                st.error(f"Error: {resp.json().get('detail', resp.text)}")
            else:
                job_id = resp.json().get("job_id")
                st.session_state["generated_job_id"] = job_id
                st.session_state["generated_company"] = company
                st.session_state["generated_role"] = role
                st.session_state["generated_result"] = None
                st.session_state["generated_status"] = "pending"
                st.info(f"Job started – ID: `{job_id}`")
                st.rerun()

    job_id = st.session_state.get("generated_job_id")
    if job_id:
        poll = _api("get", f"/status/{job_id}")
        if poll.ok:
            poll_data = poll.json()
            status = poll_data.get("status", "pending")
            st.session_state["generated_status"] = status

            if status == "done":
                st.session_state["generated_result"] = poll_data
                try:
                    meta = json.loads(poll_data.get("report", "{}"))
                except json.JSONDecodeError:
                    meta = {}

                gaps = meta.get("gaps", "")
                if gaps:
                    st.info(f"**Skill gaps detected:** {gaps}")

                st.success("✅ Documents generated! Download below.")
                if _linked:
                    st.caption("Also attached to the linked job in My Jobs.")
                col_a, col_b = st.columns(2)
                company = st.session_state.get("generated_company", "company")

                with col_a:
                    r_resp = _api("get", f"/download/resume/{job_id}")
                    if r_resp.ok:
                        st.download_button(
                            label="📄 Download Tailored Resume (.docx)",
                            data=r_resp.content,
                            file_name=f"resume_{company.replace(' ', '_')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"download_resume_{job_id}",
                        )
                    else:
                        st.error("Resume file not available.")

                with col_b:
                    c_resp = _api("get", f"/download/cover_letter/{job_id}")
                    if c_resp.ok:
                        st.download_button(
                            label="✉️ Download Cover Letter (.docx)",
                            data=c_resp.content,
                            file_name=f"cover_letter_{company.replace(' ', '_')}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"download_cover_{job_id}",
                        )
                    else:
                        st.error("Cover letter file not available.")
            elif status == "failed":
                st.error(f"Generation failed: {poll_data.get('report', '')}")
                st.session_state["generated_job_id"] = None
            else:
                st.info("Still processing. The backend is generating your files…")
                st.spinner("Working…")
                time.sleep(2)
                st.rerun()
        else:
            st.warning("Could not reach the job status endpoint yet.")
            time.sleep(2)
            st.rerun()
