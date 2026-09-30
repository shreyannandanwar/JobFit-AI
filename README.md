# JobFit AI

> **JobFit AI is a free, open-source personal job workspace that lets users maintain their career profile, manage job applications, understand each opportunity through AI-powered job and company intelligence, generate tailored application materials, and prepare for interviews — all from one place.**

Today, JobFit AI ships as the **AI engine** for that vision: a resume tailoring and document generation tool that turns a candidate resume and job description into a structured profile, a job-fit analysis, a tailored resume, and a cover letter. The rest of the platform — a job tracker, per-job workspaces, a dashboard, and multi-user accounts — is the direction the project is actively growing toward (see [Product Vision & Roadmap](#product-vision--roadmap)).

The project combines a FastAPI backend, a Streamlit interface, LangGraph workflows, and local persistence to keep the system simple to run while still providing auditable outputs.

## The Product Loop

```
BUILD PROFILE → ADD JOB → UNDERSTAND JOB → ANALYZE FIT → TAILOR APPLICATION
     → PREPARE → APPLY → TRACK → UPDATE STATUS → LEARN → ADD NEXT JOB
```

JobFit AI's resume parser, project intelligence, LangGraph workflows, company research, tailored document generation, and evaluation system are the AI engine underneath this loop, rather than being the product itself.

## What It Does Today

- Extracts structured profile data from an uploaded resume PDF.
- Parses and normalizes project details from pasted text, PDF, or DOCX content.
- Runs a job-description analysis workflow to identify skills, gaps, and supporting evidence.
- Generates tailored resume bullets and a custom cover letter.
- Exports the final documents as DOCX files.
- Stores profile data, project data, and audit logs locally for traceability.

## Architecture

The application is organized around a small number of clear layers:

- `app/main.py` exposes the FastAPI endpoints for setup, generation, status checks, and file download.
- `app/core/graph.py` defines the two LangGraph pipelines: one for gap analysis and one for document tailoring.
- `app/core/nodes.py` contains the node implementations for planning, research, verification, drafting, and export.
- `app/core/profile_parser.py` extracts resume sections and structured project records.
- `app/core/profile_store.py` persists profile and project data under `profiles/`.
- `app/core/markdown_exporter.py` writes profile sections and project exports to markdown and JSON.
- `app/core/docx_generator.py` renders the final resume and cover letter as DOCX files.
- `app/core/memory.py` stores audit logs and job status in SQLite.
- `streamlit_app.py` provides the user-facing setup and generation experience.

## Key Features

### Profile Setup

- Upload a resume PDF and automatically extract contact information, skills, education, experience, summary content, and project sections.
- Save the parsed profile as reusable structured data.
- Export profile sections into readable markdown files for inspection and reuse.

### Project Ingestion

- Accept project information from pasted text, PDF, DOCX, or structured JSON.
- Normalize project titles, descriptions, links, and technologies.
- Deduplicate repeated project entries before persistence.

### Job Analysis

- Identify a company name and a small set of required skills from the job description.
- Search the web for company-relevant evidence using DuckDuckGo.
- Verify the strength of findings before generating the final report.
- Store every step of the workflow in an SQLite audit trail.

### Document Generation

- Load the saved profile and selected projects.
- Tailor resume bullets to the target role.
- Draft a company-specific cover letter.
- Export both documents to DOCX for download.
- Fall back to deterministic generation when an LLM is not configured or returns weak output.

### LLM Support

The generation pipeline supports multiple OpenAI-compatible providers:

- OpenAI
- OpenRouter
- Ollama
- GitHub Models

## Data Flow

1. A user uploads a resume in the Streamlit app or via the API.
2. The backend parses the resume and writes a structured profile to `profiles/user_profile.json`.
3. Optional project data is parsed and stored in `profiles/user_projects.json` and `output/profile/projects.json`.
4. The analysis workflow reviews the job description, gathers external evidence, and records results in SQLite.
5. The generation workflow loads the saved profile, researches the target company, creates tailored content, and exports DOCX files to `output/generated/`.
6. The UI polls job status and surfaces the final artifacts for download.

## Repository Layout

- `app/` contains the FastAPI app and all core business logic.
- `app/core/` contains parsing, graph orchestration, export, LLM, storage, and utility modules.
- `profiles/` stores saved profile and project JSON.
- `output/profile/` stores markdown and JSON exports of the parsed profile.
- `output/generated/` stores generated resume and cover letter DOCX files.
- `tests/` contains regression coverage for project parsing, markdown export, and resume generation behavior.
- `eval/` is reserved for future evaluation tooling.

## Local Setup

### Prerequisites

- Python 3.11+
- pip
- Optional: Docker and Docker Compose

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Run the Streamlit UI

```bash
streamlit run streamlit_app.py
```

By default, the Streamlit app expects the backend at `http://localhost:8000`.

## API Endpoints

### Setup

- `POST /setup/profile` parses an uploaded resume PDF and saves the structured profile.
- `POST /setup/projects` saves project data from text, PDF, DOCX, or JSON.
- `GET /setup/status` reports whether profile setup is complete.

### Generate

- `POST /generate` starts tailored resume and cover letter generation.
- `GET /status/{job_id}` returns background job status and report data.
- `GET /download/{doc_type}/{job_id}` downloads the generated DOCX file.

## Testing

Run the test suite with:

```bash
pytest
```

The current tests focus on:

- project parsing and export behavior
- markdown regeneration and structure preservation
- resume tailoring heuristics
- cover letter fallback behavior
- plagiarism-risk reduction helpers

## Deployment

The repository includes container support for local or platform-based deployment:

- `Dockerfile` defines the application image.
- `docker-compose.yml` runs the backend with a local volume for persistence.
- `railway.json` provides Railway deployment configuration.

## Notes

- The app keeps data local and lightweight by design.
- SQLite is used for audit logging and job status tracking.
- LLM output is treated as optional rather than mandatory, so the system can still produce usable documents without external model access.

## Product Vision & Roadmap

The long-term goal is to evolve JobFit AI from a single-resume tailoring tool into a full personal job-search platform. The current codebase (profile parsing, project intelligence, job analysis, tailored generation) becomes the AI engine that powers the features below.

### Career Space (profile as the source of truth)

- A single, reusable career profile (personal info, summary, skills, projects, experience, education, certifications, activities) instead of re-uploading a resume for every application.
- The existing profile parser already extracts most of these fields, so this is an extension of the current system rather than a rewrite.

### Job Workspace (the central screen)

- A job spreadsheet/tracker (company, role, status, location, match score, deadline) as the main entry point, similar to a Notion/Sheets-style tracker with AI intelligence attached.
- Each row opens a per-job workspace containing the job description, company intelligence, fit analysis, generated resume/cover letter, preparation notes, and activity — so nothing about an application is ever lost.
- Application lifecycle statuses: `Saved → Preparing → Applied → Assessment → Interview → Offer`, plus `Rejected`, `Withdrawn`, and `Archived`.

### Job & Company Intelligence

- Extract explicit requirements from a job description (required vs. preferred skills).
- Surface inferred/latent signals ("potential expectations") transparently, explaining *why* the system reached a conclusion rather than asserting it as fact.
- Compare the candidate profile against the job across multiple dimensions (technical, experience, project, skill coverage, domain alignment) instead of collapsing fit into a single arbitrary match percentage.
- Rank the user's projects by relevance to a target role, building on the existing project parsing and relevance logic.

### Tailored Generation & Preparation

- Generate a resume and cover letter scoped to a specific company/role, using only information present in the user's profile — building directly on today's tailoring and DOCX export pipeline.
- A "Prepare for this job" view with likely technical topics, project-discussion talking points, and potential interview questions, framed as preparation material rather than guaranteed predictions.

### Dashboard

- A home view answering "Where am I in my job search?" — total/active applications, interviews, offers, and recent jobs — alongside the profile.

### Platform & Cost Architecture

- Moving from local JSON/SQLite storage to multi-user accounts with persistent, per-user job spaces is the biggest architectural shift this roadmap implies.
- Because the goal is to stay free for users, the platform should favor free-tier auth/hosting/database options and avoid having a single API key fund unlimited AI generation for every user — for example, by supporting user-provided API keys/local models alongside hosted defaults.
- The existing LLM abstraction (OpenAI, OpenRouter, Ollama, GitHub Models) is already a useful foundation for this "bring your own model" approach.

This roadmap also broadens what Hacktoberfest contributors can work on — not just "add a feature to a resume generator," but help build an open-source AI job-management platform.

## demo
<img width="1210" height="672" alt="Screenshot 2026-08-05 at 12 39 07 PM" src="https://github.com/user-attachments/assets/cf560c13-8a5e-49b2-af90-2f3136e40316" />
interface - The platform


<img width="1379" height="681" alt="Screenshot 2026-08-05 at 12 40 31 PM" src="https://github.com/user-attachments/assets/7207a18c-f531-45d5-b483-2dd82fa691c0" />
Generation of Documents

## Contributing

We welcome contributions from developers of all experience levels.

### New to open source?

Start with issues labelled:

- `good first issue`
- `help wanted`
- `documentation`
- `testing`

Before starting work:

1. Read `CONTRIBUTING.md`
2. Find an open issue
3. Comment that you'd like to work on it
4. Wait for confirmation/assignment
5. Create your branch
6. Make your changes
7. Run the tests
8. Open a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed instructions.

## 🎃 Hacktoberfest

JobFit AI welcomes contributors during Hacktoberfest.

You can contribute through:

- Python development
- Streamlit UI
- Job workspace / job tracker features
- Job and company intelligence
- Testing
- Documentation
- Resume/project parsing
- AI/LLM improvements
- Bug fixes
- Developer tooling

If you're new to open source, look for issues labelled
`good first issue`.
