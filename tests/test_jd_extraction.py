import json

from app.core import jd_extraction as jx
from app.core.jd_extraction import extract_jd, fallback_extract

JD = """Senior Backend Engineer

About us
We build payments infrastructure.

What you'll do:
- Design and operate REST APIs in Python and FastAPI
- Deploy services on K8s and AWS

Requirements:
- 5+ years of experience building backend systems
- Strong Python, PostgreSQL and Docker skills
- Familiarity with CI/CD pipelines

Nice to have:
- Experience with Kafka
- Terraform or Golang
"""


def test_fallback_sections_aliases_and_evidence():
    r = fallback_extract(JD, "Senior Backend Engineer")
    assert {"python", "postgresql", "docker", "ci/cd", "fastapi", "kubernetes", "aws"} <= set(r.required_skills)
    assert set(r.preferred_skills) == {"kafka", "terraform", "go"}
    assert "Kafka" in r.evidence["kafka"]
    assert "K8s" in r.evidence["kubernetes"]
    assert all(snippet in JD for snippet in r.evidence.values())
    assert r.seniority == "senior" and r.role_family == "backend" and r.method == "fallback"
    assert any("5+ years" in q for q in r.qualifications)
    assert any("REST APIs" in x for x in r.responsibilities)


def test_fallback_word_boundaries_and_no_invented_defaults():
    r = fallback_extract("We will go to market with a javascript heavy product. R&D team. Pythonic style.")
    assert r.required_skills == ["javascript"]
    assert fallback_extract("Be kind and curious.").required_skills == []


def test_fallback_inline_preferred_and_case_sensitive_go():
    r = fallback_extract("Must know Python. Experience with Go is a plus.")
    assert r.required_skills == ["python"] and r.preferred_skills == ["go"]


def test_required_wins_over_preferred():
    r = fallback_extract("Requirements:\n- Python\nNice to have:\n- Python, Docker")
    assert r.required_skills == ["python"] and r.preferred_skills == ["docker"]


def test_seniority_and_family_inference():
    assert jx.infer_seniority("", "Software Engineering Intern") == "intern"
    assert jx.infer_seniority("entry-level role") == "junior"
    assert jx.infer_seniority("3+ years of experience") == "mid"
    assert jx.infer_seniority("nothing here") == "unknown"
    assert jx.infer_role_family("Build LLM and PyTorch models", "ML Engineer") == "ml"
    assert jx.infer_role_family("full-stack web app") == "fullstack"


CFG = {"provider": "openai", "model": "m"}


def _stub_llm(monkeypatch, payload, calls):
    def fake(messages, cfg, **kw):
        calls.append(1)
        return payload if isinstance(payload, str) else "```json\n" + json.dumps(payload) + "\n```"
    monkeypatch.setattr("app.core.llm.llm_chat", fake)


def test_llm_output_is_grounded_and_cached(monkeypatch):
    calls = []
    _stub_llm(monkeypatch, {
        "required_skills": ["Python", "K8s", "Quantum Gardening"],
        "preferred_skills": ["Kafka"],
        "responsibilities": ["Operate APIs"],
        "qualifications": ["5+ years"],
        "seniority": "senior", "role_family": "backend",
        "evidence": {"Python": "Strong Python, PostgreSQL and Docker skills", "Kafka": "made up quote"},
    }, calls)
    r = extract_jd(JD, CFG)
    assert r.method == "llm"
    assert r.required_skills == ["python", "kubernetes"]  # hallucinated skill dropped, K8s canonicalized
    assert r.preferred_skills == ["kafka"]
    assert r.evidence["python"] == "Strong Python, PostgreSQL and Docker skills"
    assert "Kafka" in r.evidence["kafka"]  # fabricated quote replaced with a real JD line
    again = extract_jd(JD, CFG)
    assert again == r and len(calls) == 1


def test_llm_failure_falls_back(monkeypatch):
    for bad in ("", "not json", '{"required_skills": ["Cobol"]}'):
        _stub_llm(monkeypatch, bad, [])
        assert extract_jd(JD + bad, CFG).method == "fallback"


def test_no_llm_config_never_calls_llm(monkeypatch):
    calls = []
    _stub_llm(monkeypatch, {}, calls)
    assert extract_jd(JD, None).method == "fallback" and not calls


def test_invalid_llm_enums_are_replaced(monkeypatch):
    _stub_llm(monkeypatch, {"required_skills": ["Python"], "seniority": "wizard", "role_family": "magic",
                            "evidence": {}}, [])
    r = extract_jd(JD, CFG)
    assert r.seniority == "senior" and r.role_family == "backend"
