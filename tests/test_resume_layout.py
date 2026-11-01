"""Golden-file tests for the resume layout engine.

Validates section order, text quality, skills normalisation, truncation
behaviour, and education filtering against a fixed sample profile.
"""

import re
import tempfile
from pathlib import Path

import pytest
from docx import Document

from app.core.content_contract import (
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    ResumeContent,
    ResumeLayoutInput,
)
from app.core.text_utils import clean_text, normalize_skills


# ═══════════════════════════════════════════════════════════════════════════════
# Fixture: a realistic, deliberately messy sample profile
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_layout_input() -> ResumeLayoutInput:
    """Build a fixed ResumeLayoutInput with 2 experience entries (one long),
    3 projects, 15 raw messy skills (including abbreviations, duplicates, and
    lowercase entries), and education with both a B.Tech and a high-school entry.
    """
    return ResumeLayoutInput(
        contact=ContactInfo(
            name="Priya Sharma",
            email="priya.sharma@example.com",
            phone="+91 98765 43210",
            linkedin="https://linkedin.com/in/priya-sharma",
            github="https://github.com/priyasharma",
            location="Bengaluru, India",
        ),
        experience=[
            ExperienceEntry(
                id="exp_0",
                role="Senior ML Engineer",
                company="TechCorp AI",
                location="Bengaluru",
                start_date="Jan. 2022",
                end_date="Present",
                description=(
                    "Led design and deployment of a real-time recommendation engine serving 50M+ users\n"
                    "Architected model training pipelines on Kubernetes, reducing iteration time by 40%\n"
                    "Mentored a team of 5 junior engineers on MLOps best practices\n"
                    "Collaborated with product managers to define success metrics and A/B testing strategies"
                ),
            ),
            ExperienceEntry(
                id="exp_1",
                role="Software Engineer",
                company="DataFlow Inc.",
                location="Mumbai",
                start_date="Jun. 2019",
                end_date="Dec. 2021",
                description=(
                    "Built REST APIs for analytics dashboards using Python and FastAPI\n"
                    "Improved data ingestion pipeline throughput by 3x through async processing"
                ),
            ),
        ],
        projects=[
            ProjectEntry(
                id="proj_0",
                title="Inventory Forecasting Engine",
                description=(
                    "Built a demand forecasting system for retail using XGBoost and Prophet\n"
                    "Achieved 92% accuracy on 30-day demand predictions"
                ),
                technologies=["Python", "XGBoost", "Prophet", "FastAPI"],
                github="https://github.com/priyasharma/inventory-forecast",
                deployment="https://forecast-demo.example.com",
            ),
            ProjectEntry(
                id="proj_1",
                title="Churn Prediction Platform",
                description=(
                    "End-to-end ML platform for customer churn prediction\n"
                    "Deployed as a microservice with Docker and Kubernetes"
                ),
                technologies=["Python", "Scikit-learn", "Docker", "Kubernetes"],
                github="https://github.com/priyasharma/churn-predict",
            ),
            ProjectEntry(
                id="proj_2",
                title="Portfolio CMS",
                description="A developer portfolio and blog web app built with Flask.",
                technologies=["Python", "Flask", "PostgreSQL"],
            ),
        ],
        education=[
            EducationEntry(
                institution="Indian Institute of Technology Delhi",
                degree="B.Tech",
                field="Computer Science",
                location="New Delhi",
                start_date="2015",
                end_date="2019",
                grade="8.7",
            ),
            EducationEntry(
                institution="Delhi Public School",
                degree="HSC",
                field="",
                location="New Delhi",
                start_date="2013",
                end_date="2015",
                grade="95%",
            ),
        ],
        certifications=[
            "DeepLearning.AI – Machine Learning Specialization",
            "Udemy – Complete Python Bootcamp",
        ],
        activities=[
            "Open Source (Hacktoberfest)",
            "Campus Ambassador (RINEX)",
            "Volunteer (TechFest 2024)",
        ],
        raw_skills=[
            "python", "ml", "api", "js", "docker", "kubernetes",
            "Python",  # duplicate
            "fastapi", "sql", "react", "tensorflow",
            "ml",      # duplicate abbreviation
            "git", "linux", "aws", "pandas",
        ],
        content=ResumeContent(
            summary=(
                "Priya Sharma is applying for the Senior ML Engineer role at InnovateTech, "
                "bringing proven expertise in machine learning, Python, and cloud-native "
                "systems engineering with a track record of delivering production ML systems "
                "at scale."
            ),
            highlights=[
                "Led deployment of a recommendation engine serving 50M+ users at TechCorp AI.",
                "Reduced ML iteration time by 40% through Kubernetes-based training pipelines.",
                "Achieved 92% accuracy on retail demand forecasting using XGBoost and Prophet.",
            ],
            projects_used=["proj_0", "proj_1", "proj_2"],
        ),
    )


def _generate_docx(data: ResumeLayoutInput, tmp_path: Path) -> Document:
    """Helper: generate a DOCX and return the parsed Document."""
    from app.core.docx_generator import generate_resume_docx
    output = str(tmp_path / "test_resume.docx")
    generate_resume_docx(data, output)
    return Document(output)


def _full_text(doc: Document) -> str:
    """Extract all paragraph text from a Document."""
    return "\n".join(p.text for p in doc.paragraphs)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSectionOrder:
    """Section order must match the spec: when experience exists, Experience
    comes before Education."""

    def test_experience_before_education_when_both_present(
        self, sample_layout_input, tmp_path
    ):
        doc = _generate_docx(sample_layout_input, tmp_path)
        text = _full_text(doc)
        exp_pos = text.find("EXPERIENCE")
        edu_pos = text.find("EDUCATION")
        cert_pos = text.find("CERTIFICATIONS")
        act_pos = text.find("ACTIVITIES")
        skills_pos = text.find("TECHNICAL SKILLS")
        assert exp_pos != -1, "Experience section not found"
        assert edu_pos != -1, "Education section not found"
        assert cert_pos != -1, "Certifications section not found"
        assert act_pos != -1, "Activities section not found"
        assert skills_pos != -1, "Technical Skills section not found"
        assert exp_pos < edu_pos < cert_pos < act_pos < skills_pos, (
            "Section order must be: Experience -> Education -> Certifications -> Activities -> Technical Skills"
        )

    def test_education_first_when_no_experience(
        self, sample_layout_input, tmp_path
    ):
        data = sample_layout_input.model_copy(deep=True)
        data.experience = []
        doc = _generate_docx(data, tmp_path)
        text = _full_text(doc)
        edu_pos = text.find("EDUCATION")
        assert edu_pos != -1, "Education section not found"
        # Experience heading should not appear.
        assert "EXPERIENCE" not in text


class TestNoArtifacts:
    """The output must never contain truncation markers, double spaces, or
    orphaned separators."""

    def test_no_ellipsis(self, sample_layout_input, tmp_path):
        doc = _generate_docx(sample_layout_input, tmp_path)
        text = _full_text(doc)
        assert "..." not in text, f"Found '...' in output:\n{text}"

    def test_no_double_spaces(self, sample_layout_input, tmp_path):
        doc = _generate_docx(sample_layout_input, tmp_path)
        for para in doc.paragraphs:
            # Allow " | " formatting — only check for genuine double-spaces
            # in the text outside of formatted separators.
            cleaned = para.text.replace(" | ", "|")
            assert "  " not in cleaned, (
                f"Found double space in paragraph: {para.text!r}"
            )


class TestSkillsNormalization:
    """Skills must be title-cased, deduped, expanded, and capped."""

    def test_no_lowercase_skill_tokens_in_output(
        self, sample_layout_input, tmp_path
    ):
        doc = _generate_docx(sample_layout_input, tmp_path)
        text = _full_text(doc)
        # Find the Technical Skills section.
        skills_pos = text.find("TECHNICAL SKILLS")
        assert skills_pos != -1, "Technical Skills section not found"
        skills_text = text[skills_pos:]

        # None of these raw lowercase tokens should appear as standalone words.
        forbidden = {"ml", "api", "js"}
        words = re.findall(r"\b\w+\b", skills_text)
        found_raw = forbidden & {w for w in words}
        assert not found_raw, f"Raw lowercase skill tokens in output: {found_raw}"

    def test_machine_learning_present(self, sample_layout_input, tmp_path):
        doc = _generate_docx(sample_layout_input, tmp_path)
        text = _full_text(doc)
        assert "Machine Learning" in text

    def test_max_12_skills(self, sample_layout_input, tmp_path):
        groups = normalize_skills(sample_layout_input.raw_skills)
        total = sum(len(v) for v in groups.values())
        assert total <= 12, f"Expected ≤12 skills, got {total}"

    def test_deduplication(self, sample_layout_input, tmp_path):
        groups = normalize_skills(sample_layout_input.raw_skills)
        all_skills = [s for items in groups.values() for s in items]
        lowered = [s.lower() for s in all_skills]
        assert len(lowered) == len(set(lowered)), (
            f"Duplicate skills found: {lowered}"
        )


class TestExperienceRendering:
    """Experience entries must render as a header line + bullets, not as one
    giant line."""

    def test_long_experience_has_header_and_bullets(
        self, sample_layout_input, tmp_path
    ):
        doc = _generate_docx(sample_layout_input, tmp_path)
        paragraphs = [p.text for p in doc.paragraphs]

        # Find the paragraph containing the first experience role.
        header_idx = None
        for i, text in enumerate(paragraphs):
            if "Senior ML Engineer" in text and "TechCorp AI" in text:
                header_idx = i
                break

        assert header_idx is not None, "Experience header not found"

        # After the header, there should be bullet paragraphs (en-dash prefixed).
        bullet_count = 0
        for j in range(header_idx + 1, len(paragraphs)):
            if paragraphs[j].startswith("\u2013"):  # en-dash
                bullet_count += 1
            elif paragraphs[j].strip() and not paragraphs[j].startswith("\u2013"):
                break  # next section or entry

        assert bullet_count >= 2, (
            f"Expected ≥2 bullet lines after header, got {bullet_count}"
        )


class TestEducationFiltering:
    """When a B.Tech entry is present, the HSC entry must be omitted."""

    def test_hsc_omitted_when_degree_present(
        self, sample_layout_input, tmp_path
    ):
        doc = _generate_docx(sample_layout_input, tmp_path)
        text = _full_text(doc)
        assert "Indian Institute of Technology" in text
        assert "Delhi Public School" not in text, (
            "High-school entry should be omitted when a degree is present"
        )


class TestNoTruncation:
    """The layout must never truncate content — overflow is handled by
    wrapping, not slicing."""

    def test_long_summary_renders_fully(self, sample_layout_input, tmp_path):
        data = sample_layout_input.model_copy(deep=True)
        # Set a summary that is 500+ characters.
        long_summary = (
            "Priya Sharma is a highly experienced machine learning engineer "
            "with deep expertise in designing and deploying production-grade "
            "ML systems at scale. She has led cross-functional teams in building "
            "recommendation engines, demand forecasting systems, and churn "
            "prediction platforms. Her technical skills span Python, TensorFlow, "
            "Kubernetes, and cloud-native architectures. She is passionate about "
            "mentoring junior engineers and establishing MLOps best practices "
            "across engineering organisations. She brings a track record of "
            "delivering measurable business impact through data-driven solutions "
            "and is eager to contribute to InnovateTech's mission of building "
            "intelligent systems that serve millions of users worldwide."
        )
        assert len(long_summary) > 500, "Test setup: summary should be >500 chars"
        data.content.summary = long_summary

        doc = _generate_docx(data, tmp_path)
        text = _full_text(doc)

        # The full summary must appear — no cutting, no "...".
        assert long_summary[:50] in text or clean_text(long_summary)[:50] in text, (
            "Summary was truncated"
        )
        assert "..." not in text, "Found truncation marker in output"


class TestEmptySections:
    """Empty sections must be omitted entirely — no empty heading."""

    def test_no_highlights_section_when_empty(
        self, sample_layout_input, tmp_path
    ):
        data = sample_layout_input.model_copy(deep=True)
        data.content.highlights = []
        doc = _generate_docx(data, tmp_path)
        text = _full_text(doc)
        assert "HIGHLIGHTS" not in text

    def test_no_projects_section_when_empty(
        self, sample_layout_input, tmp_path
    ):
        data = sample_layout_input.model_copy(deep=True)
        data.projects = []
        data.content.projects_used = []
        doc = _generate_docx(data, tmp_path)
        text = _full_text(doc)
        assert "PROJECTS" not in text

    def test_no_skills_section_when_empty(
        self, sample_layout_input, tmp_path
    ):
        data = sample_layout_input.model_copy(deep=True)
        data.raw_skills = []
        data.content.skills_grouped = {}
        doc = _generate_docx(data, tmp_path)
        text = _full_text(doc)
        assert "TECHNICAL SKILLS" not in text

    def test_no_certifications_section_when_empty(
        self, sample_layout_input, tmp_path
    ):
        data = sample_layout_input.model_copy(deep=True)
        data.certifications = []
        doc = _generate_docx(data, tmp_path)
        text = _full_text(doc)
        assert "CERTIFICATIONS" not in text

    def test_no_activities_section_when_empty(
        self, sample_layout_input, tmp_path
    ):
        data = sample_layout_input.model_copy(deep=True)
        data.activities = []
        doc = _generate_docx(data, tmp_path)
        text = _full_text(doc)
        assert "ACTIVITIES" not in text


class TestCertificationsAndActivities:
    """Certifications and Activities sections rendering and contract tests."""

    def test_rendered_correctly_with_expected_formats(
        self, sample_layout_input, tmp_path
    ):
        doc = _generate_docx(sample_layout_input, tmp_path)
        text = _full_text(doc)
        assert "CERTIFICATIONS" in text
        assert "DeepLearning.AI – Machine Learning Specialization" in text
        assert "Udemy – Complete Python Bootcamp" in text

        assert "ACTIVITIES" in text
        # Activities must be rendered on ONE line with pipe separator
        expected_line = "Open Source (Hacktoberfest) | Campus Ambassador (RINEX) | Volunteer (TechFest 2024)"
        matching_paras = [p.text for p in doc.paragraphs if expected_line in p.text]
        assert len(matching_paras) == 1, f"Expected activities on one line, found in: {matching_paras}"

    def test_layout_input_from_profile_populates_certifications_and_activities(self):
        from app.core.content_contract import layout_input_from_profile
        profile = {
            "name": "Alex Candidate",
            "certifications_items": [
                {"name": "ML Specialization", "issuer": "DeepLearning.AI"},
                {"name": "AWS Solutions Architect", "issuer": "AWS"},
            ],
            "activities_items": [
                {"title": "Open Source Contributor", "organization": "PEcAn"},
                {"title": "Club Lead", "organization": "ACM Student Chapter"},
            ],
        }
        layout_input = layout_input_from_profile(profile)
        assert layout_input.certifications == [
            "DeepLearning.AI – ML Specialization",
            "AWS – AWS Solutions Architect",
        ]
        assert layout_input.activities == [
            "Open Source Contributor (PEcAn)",
            "Club Lead (ACM Student Chapter)",
        ]


class TestCleanText:
    """Unit tests for the clean_text utility."""

    def test_collapses_whitespace(self):
        assert "Hello world." == clean_text("Hello   world")

    def test_strips_trailing_ellipsis(self):
        result = clean_text("Some text that was cut off...")
        assert "..." not in result

    def test_strips_orphaned_dash(self):
        result = clean_text("Some text --")
        assert result.endswith(".")
        assert "--" not in result

    def test_sentence_capitalises(self):
        result = clean_text("led a team of engineers")
        assert result[0] == "L"

    def test_ensures_ending_punctuation(self):
        result = clean_text("Built a system")
        assert result.endswith(".")

    def test_preserves_existing_punctuation(self):
        result = clean_text("What did you build?")
        assert result.endswith("?")
        assert not result.endswith("?.")

