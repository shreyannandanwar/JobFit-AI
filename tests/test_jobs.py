from datetime import datetime, timedelta

import pytest

from fastapi.testclient import TestClient

from app.core import jobs as job_store
from app.core.memory import get_db, sweep_stale_jobs, update_job_status
from app.main import app

client = TestClient(app)


def _create(**kw):
    body = {"company": "Acme", "role": "Engineer", **kw}
    r = client.post("/jobs", json=body)
    assert r.status_code == 201
    return r.json()


def test_create_and_get_job():
    job = _create(jd_text="Python", deadline="2026-11-01")
    data = client.get(f"/jobs/{job['job_id']}").json()
    assert data["job"]["status"] == "saved"
    assert [e["event_type"] for e in data["events"]] == ["created"]


def test_create_requires_company_and_role():
    assert client.post("/jobs", json={"company": " ", "role": "x"}).status_code == 422
    assert client.post("/jobs", json={"company": "x"}).status_code == 422


def test_list_filter_by_status():
    a = _create()
    _create()
    client.patch(f"/jobs/{a['job_id']}", json={"status": "applied"})
    assert len(client.get("/jobs").json()) == 2
    assert len(client.get("/jobs?status=applied").json()) == 1
    assert client.get("/jobs?status=bogus").status_code == 422


def test_patch_status_and_notes_create_events():
    job = _create()
    jid = job["job_id"]
    r = client.patch(f"/jobs/{jid}", json={"status": "applied", "notes": "referred"})
    assert r.status_code == 200 and r.json()["status"] == "applied"
    types = [e["event_type"] for e in client.get(f"/jobs/{jid}").json()["events"]]
    assert types == ["created", "status_changed", "note_added"]


def test_patch_invalid_status_and_missing_job():
    jid = _create()["job_id"]
    assert client.patch(f"/jobs/{jid}", json={"status": "nope"}).status_code == 422
    assert client.patch("/jobs/missing", json={"notes": "x"}).status_code == 404


def test_delete_job():
    jid = _create()["job_id"]
    assert client.delete(f"/jobs/{jid}").status_code == 204
    assert client.get(f"/jobs/{jid}").status_code == 404
    assert client.delete(f"/jobs/{jid}").status_code == 404


def test_attach_generation_stores_relative_paths_and_serves_artifact(tmp_path):
    jid = _create()["job_id"]
    docx = job_store.PROJECT_ROOT / "output" / "generated" / "_test_resume.docx"
    docx.parent.mkdir(parents=True, exist_ok=True)
    docx.write_bytes(b"docx")
    try:
        job_store.attach_generation(jid, "run1", str(docx), None, "gap")
        data = client.get(f"/jobs/{jid}").json()
        resume = next(a for a in data["artifacts"] if a["kind"] == "resume")
        assert resume["file_path"] == "output/generated/_test_resume.docx"
        assert "generated" in [e["event_type"] for e in data["events"]]
        assert client.get(f"/jobs/{jid}/artifacts/resume").content == b"docx"
        assert client.get(f"/jobs/{jid}/artifacts/cover_letter").status_code == 404
    finally:
        docx.unlink()


def test_generate_rejects_unknown_job_id(monkeypatch):
    monkeypatch.setattr("app.core.profile_store.profile_exists", lambda: True)
    r = client.post("/generate", data={"jd": "x", "company": "c", "role": "r", "job_id": "nope"})
    assert r.status_code == 404


def test_resolve_generation_inputs_reconciliation():
    from app.main import GenerateForm, resolve_generation_inputs

    job = {"company": "Acme", "role": "Engineer", "jd_text": "Stored JD"}
    # Empty form fields -> base values win
    res = resolve_generation_inputs(job, GenerateForm(company="", role="", jd=""))
    assert res["company"] == "Acme"
    assert res["role"] == "Engineer"
    assert res["jd_text"] == "Stored JD"
    assert res["overrides"] == {}
    assert res["jd_source"] == "stored_value"

    # Form overrides JD
    res = resolve_generation_inputs(job, GenerateForm(company="", role="", jd="New JD"))
    assert res["jd_text"] == "New JD"
    assert res["overrides"] == {"jd_text": "New JD"}
    assert res["jd_source"] == "form_override"

    # No job provided -> form used as-is
    res = resolve_generation_inputs(None, GenerateForm(company="Beta", role="Dev", jd="Dev JD"))
    assert res["company"] == "Beta"
    assert res["overrides"] == {}
    assert res["jd_source"] == "form"


def test_generate_with_job_id_and_empty_jd_uses_stored_jd(monkeypatch):
    from unittest.mock import MagicMock
    import json
    monkeypatch.setattr("app.core.profile_store.profile_exists", lambda: True)
    job = _create(company="Acme", role="Engineer", jd_text="Stored Job Description for Acme")
    jid = job["job_id"]

    mock_invoke = MagicMock(return_value={
        "resume_docx_path": "output/generated/dummy_resume.docx",
        "cover_letter_docx_path": "output/generated/dummy_cover.docx",
        "gap_analysis": "None",
    })
    monkeypatch.setattr("app.main.tailoring_graph.invoke", mock_invoke)

    r = client.post("/generate", data={"job_id": jid, "jd": "", "company": "", "role": ""})
    assert r.status_code == 200

    # Verify mock_invoke received stored jd_text
    args, kwargs = mock_invoke.call_args
    assert args[0]["jd_text"] == "Stored Job Description for Acme"
    assert args[0]["company_name"] == "Acme"
    assert args[0]["role_title"] == "Engineer"

    # Verify job events recorded stored_value
    events = client.get(f"/jobs/{jid}").json()["events"]
    gen_event = next(e for e in events if e["event_type"] == "generated")
    detail = json.loads(gen_event["detail"]) if isinstance(gen_event["detail"], str) else gen_event["detail"]
    assert detail.get("jd_source") == "stored_value"


def test_generate_with_job_id_and_different_jd_overrides_and_updates_job(monkeypatch):
    from unittest.mock import MagicMock
    import json
    monkeypatch.setattr("app.core.profile_store.profile_exists", lambda: True)
    job = _create(company="Acme", role="Engineer", jd_text="Original JD")
    jid = job["job_id"]

    mock_invoke = MagicMock(return_value={
        "resume_docx_path": "output/generated/dummy_resume.docx",
        "cover_letter_docx_path": "output/generated/dummy_cover.docx",
        "gap_analysis": "None",
    })
    monkeypatch.setattr("app.main.tailoring_graph.invoke", mock_invoke)

    r = client.post("/generate", data={"job_id": jid, "jd": "Overridden Form JD", "company": "", "role": ""})
    assert r.status_code == 200

    # Verify graph invoked with overridden JD
    args, _ = mock_invoke.call_args
    assert args[0]["jd_text"] == "Overridden Form JD"

    # Verify job row was updated in tracker
    updated_job = client.get(f"/jobs/{jid}").json()["job"]
    assert updated_job["jd_text"] == "Overridden Form JD"

    # Verify job event recorded form_override
    events = client.get(f"/jobs/{jid}").json()["events"]
    gen_event = next(e for e in events if e["event_type"] == "generated")
    detail = json.loads(gen_event["detail"]) if isinstance(gen_event["detail"], str) else gen_event["detail"]
    assert detail.get("jd_source") == "form_override"


def test_generate_without_job_id_unchanged_behavior(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr("app.core.profile_store.profile_exists", lambda: True)

    mock_invoke = MagicMock(return_value={
        "resume_docx_path": "output/generated/dummy_resume.docx",
        "cover_letter_docx_path": "output/generated/dummy_cover.docx",
        "gap_analysis": "None",
    })
    monkeypatch.setattr("app.main.tailoring_graph.invoke", mock_invoke)

    r = client.post("/generate", data={"jd": "OneOff JD", "company": "OneOff Co", "role": "OneOff Role"})
    assert r.status_code == 200

    args, _ = mock_invoke.call_args
    assert args[0]["jd_text"] == "OneOff JD"
    assert args[0]["company_name"] == "OneOff Co"
    assert args[0]["role_title"] == "OneOff Role"


def test_sweep_marks_stale_processing_runs():
    update_job_status("old", "processing")
    update_job_status("new", "processing")
    old = (datetime.now() - timedelta(hours=2)).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE job_results SET created_at = ? WHERE job_id = 'old'", (old,))
        conn.commit()
    assert sweep_stale_jobs(30) == 1
    with get_db() as conn:
        rows = {r["job_id"]: r["status"] for r in conn.execute("SELECT job_id, status FROM job_results")}
    assert rows == {"old": "interrupted", "new": "processing"}


def test_migrations_are_idempotent():
    from app.core.memory import init_db
    init_db()
    init_db()
    with get_db() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3


@pytest.fixture
def profile_dir(tmp_path, monkeypatch):
    import app.core.profile_store as ps
    monkeypatch.setattr(ps, "_PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(ps, "_PROFILE_PATH", str(tmp_path / "p.json"))
    monkeypatch.setattr(ps, "_PROJECTS_PATH", str(tmp_path / "pr.json"))
    return ps


def test_profile_multi_entry_sections(profile_dir):
    assert client.get("/profile").json()["skills"] == []
    r = client.put("/profile", json={
        "name": "Ada",
        "skill_groups": [
            {"category": "Languages", "skills": ["Python", " python ", "SQL", ""]},
            {"category": "Tools", "skills": ["Docker", "sql"]},
        ],
        "experience_items": [
            {"role": "Engineer", "company": "Acme", "start_date": "2024", "end_date": "2025",
             "description": "Built APIs"},
            {"role": "Intern", "company": "Beta"},
            {"role": "", "company": "ignored"},
        ],
        "education_items": [{"degree": "B.Tech", "institution": "XYZ Univ", "field": "CS", "grade": "9.0"}],
        "certifications_items": [{"name": "AWS SAA", "issuer": "Amazon"}],
        "activities_items": [{"title": "Hackathon", "organization": "ACM"}],
        "projects": [{"title": "P1", "description": "d", "technologies": ["Py"]}],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["skills"] == ["Python", "SQL", "Docker"]
    assert [g["category"] for g in data["skill_groups"]] == ["Languages", "Tools"]
    assert len(data["experience_items"]) == 2
    assert len(data["education_items"]) == 1 and len(data["certifications_items"]) == 1
    assert data["projects"][0]["title"] == "P1"

    # Flat text the generation pipeline reads is re-rendered from the entries.
    flat = ps_load(profile_dir)
    assert "Engineer at Acme" in flat["experience"] and "Built APIs" in flat["experience"]
    assert "B.Tech in CS" in flat["education"] and "XYZ Univ" in flat["education"]
    assert "AWS SAA" in flat["certifications"]

    r = client.put("/profile", json={"summary": "Hi"})
    assert r.json()["name"] == "Ada" and r.json()["summary"] == "Hi"
    assert len(r.json()["experience_items"]) == 2


def ps_load(ps):
    return ps.load_profile()


def test_profile_seeds_entries_from_legacy_text(profile_dir):
    profile_dir.save_profile({
        "name": "Old", "skills": ["python"],
        "experience": "Dev at X\nBuilt things\n\nIntern at Y",
        "education": "B.Tech",
    })
    data = client.get("/profile").json()
    assert [e["role"] for e in data["experience_items"]] == ["Dev at X", "Intern at Y"]
    assert data["experience_items"][0]["description"] == "Built things"
    assert data["education_items"][0]["institution"] == "B.Tech"
    assert data["skill_groups"] == [{"category": "General", "skills": ["python"]}]


def test_profile_rejects_untitled_project(profile_dir):
    assert client.put("/profile", json={"projects": [{"title": " "}]}).status_code == 422


def test_certifications_seed_one_per_line_with_url(profile_dir):
    profile_dir.save_profile({"certifications": "DeepLearning.AI – ML Specialization [https://x.io/c1]\nPython Bootcamp"})
    items = client.get("/profile").json()["certifications_items"]
    assert items[0] == {"name": "ML Specialization", "issuer": "DeepLearning.AI",
                        "date": "", "credential_url": "https://x.io/c1"}
    assert items[1]["name"] == "Python Bootcamp"
