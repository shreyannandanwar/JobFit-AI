from pathlib import Path

from app.core.markdown_exporter import export_projects_to_markdown, rewrite_markdown_file_with_ai


def test_rewrite_markdown_file_preserves_project_sections(tmp_path):
    path = tmp_path / "projects.md"
    path.write_text(
        "# Projects\n\n"
        "## Project One\n\n"
        "Some details about project one.\n\n"
        "## Project Two\n\n"
        "Some details about project two.\n",
        encoding="utf-8",
    )

    rewritten_path = rewrite_markdown_file_with_ai(path, llm_cfg=None)
    rewritten = Path(rewritten_path).read_text(encoding="utf-8")

    assert "## Project One" in rewritten
    assert "## Project Two" in rewritten
    assert rewritten.count("## ") >= 2


def test_rewrite_skills_file_mentions_projects_reference(tmp_path):
    projects_path = tmp_path / "projects.md"
    projects_path.write_text(
        "# Projects\n\n"
        "## Project One\n\n"
        "Details one\n",
        encoding="utf-8",
    )

    skills_path = tmp_path / "skills.md"
    skills_path.write_text("# Skills\n\n- Python\n- SQL\n", encoding="utf-8")

    rewrite_markdown_file_with_ai(skills_path, llm_cfg=None)
    rewritten = skills_path.read_text(encoding="utf-8")

    assert "projects.md" in rewritten.lower() or "project portfolio" in rewritten.lower()


def test_export_projects_to_markdown_uses_structured_sections(tmp_path):
    project = {
        "title": "Event Schema Registry & Immutable Audit Pipeline",
        "description": "An event-driven platform for validating and auditing business events.",
        "github": "https://github.com/example/schema-registry",
        "deployment": "https://example.com/schema-registry",
        "technologies": ["Java", "Spring Boot", "PostgreSQL", "React", "Docker"],
        "key_features": ["Immutable append-only audit log", "JSON schema validation"],
        "why": "To demonstrate production-grade event sourcing without heavyweight infrastructure.",
        "problem": "It preserves a complete history of state changes for compliance and debugging.",
        "unique": ["Combines event sourcing with schema validation", "Provides a visual trace timeline"],
        "technical_explanation": ["Uses Spring Boot and PostgreSQL", "Materializes state projections"],
        "tech_stack": ["Java", "Spring Boot", "PostgreSQL", "React", "Docker"],
    }

    output_path = export_projects_to_markdown([project], output_dir=str(tmp_path))
    content = Path(output_path).read_text(encoding="utf-8")

    assert "## Links" in content
    assert "## Description" in content
    assert "## Key Features" in content
    assert "## Why?" in content
    assert "## What Problem Does It Solve?" in content
    assert "## Why Is This Project Unique?" in content
    assert "## Technical Explanation" in content
    assert "## Tech Stack" in content
    assert "https://github.com/example/schema-registry" in content
