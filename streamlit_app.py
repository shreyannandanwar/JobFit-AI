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
tab_setup, tab_generate = st.tabs(["⚙️ Setup Profile", "🚀 Generate Documents"])

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
# TAB 2 – GENERATE
# =============================================================================
with tab_generate:
    if not profile_ready:
        st.warning("Complete the **Setup** tab first before generating documents.")
        st.stop()

    st.header("Generate Tailored Resume & Cover Letter")

    with st.form("generate_form"):
        col1, col2 = st.columns([1, 1])
        with col1:
            company = st.text_input("Company Name *", placeholder="e.g. Stripe")
            role = st.text_input("Role Title *", placeholder="e.g. Senior Backend Engineer")
        with col2:
            jd = st.text_area("Job Description *", height=220, placeholder="Paste the full job description here…")
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
