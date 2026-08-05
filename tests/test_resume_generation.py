import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.docx_generator import select_relevant_projects, summarize_experience
from app.core.nodes import cover_letter_node
from app.core.plagiarism_reducer import reduce_plagiarism_risk
from app.core.state import TailoringState


class ResumeGenerationTests(unittest.TestCase):
    def test_select_relevant_projects_prefers_role_match(self):
        projects = [
            {
                "title": "Portfolio CMS",
                "description": "A developer portfolio and blog web app",
                "technologies": ["Python", "Flask"],
            },
            {
                "title": "Inventory Forecasting Engine",
                "description": "Demand forecasting and optimization for retail",
                "technologies": ["Python", "XGBoost", "Prophet"],
            },
            {
                "title": "Churn Prediction Platform",
                "description": "ML platform for churn and retention",
                "technologies": ["Python", "Scikit-learn"],
            },
        ]

        selected = select_relevant_projects(
            projects,
            role_title="Machine Learning Engineer",
            jd_text="Build forecasting models, deploy ML systems, and work with Python and XGBoost",
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["title"], "Inventory Forecasting Engine")
        self.assertEqual(selected[1]["title"], "Churn Prediction Platform")

    def test_summarize_experience_truncates_to_selected_bullets(self):
        experience = "\n".join([
            "Built REST APIs for analytics products",
            "Led deployment automation for cloud services",
            "Improved model pipelines and observability",
            "Mentored software engineers across the team",
        ])

        summary = summarize_experience(experience, max_items=3)

        self.assertEqual(len(summary), 3)
        self.assertIn("Built REST APIs", summary[0])
        self.assertIn("Led deployment automation", summary[1])
        self.assertIn("Improved model pipelines", summary[2])

    def test_cover_letter_falls_back_when_llm_returns_signature_only(self):
        state = TailoringState(
            job_id="demo",
            jd_text="Build backend systems with Python and APIs",
            company_name="Acme",
            role_title="Software Engineer",
            user_profile={
                "name": "Alex Doe",
                "skills": ["python", "api", "docker"],
                "experience": "Built REST APIs for analytics products. Led deployment automation.",
            },
            company_findings=[],
            tailored_bullets=[],
            cover_letter_text=None,
            gap_analysis=None,
            resume_docx_path=None,
            cover_letter_docx_path=None,
            llm_config={"provider": "openrouter"},
            iteration=0,
            max_iterations=2,
            status="running",
        )

        with patch("app.core.llm.llm_chat", return_value="**Alex Doe**\n\nSincerely,\nAlex Doe"):
            result = cover_letter_node(state)

        self.assertIn("Acme", result["cover_letter_text"])
        self.assertIn("contributing", result["cover_letter_text"])

    def test_cover_letter_uses_relevant_projects_from_projects_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_path = Path(tmpdir) / "projects.json"
            projects_path.write_text(json.dumps([
                {
                    "title": "Portfolio CMS",
                    "description": "A developer portfolio and blog platform built with Flask and PostgreSQL.",
                    "technologies": ["Python", "Flask"],
                },
                {
                    "title": "Inventory Forecasting Engine",
                    "description": "A forecasting system for retail demand planning using Python and XGBoost.",
                    "technologies": ["Python", "XGBoost"],
                },
            ]), encoding="utf-8")

            state = TailoringState(
                job_id="demo",
                jd_text="Build backend systems with Python and APIs",
                company_name="Acme",
                role_title="Software Engineer",
                user_profile={
                    "name": "Alex Doe",
                    "skills": ["python", "api", "docker"],
                    "experience": "Built REST APIs for analytics products. Led deployment automation.",
                },
                company_findings=[],
                tailored_bullets=[],
                cover_letter_text=None,
                gap_analysis=None,
                resume_docx_path=None,
                cover_letter_docx_path=None,
                llm_config={"provider": ""},
                iteration=0,
                max_iterations=2,
                status="running",
            )

            with patch("app.core.nodes._get_project_store_path", return_value=projects_path):
                result = cover_letter_node(state)

            self.assertIn("Portfolio CMS", result["cover_letter_text"])
            self.assertIn("developer portfolio", result["cover_letter_text"])

    def test_reduce_plagiarism_risk_rewrites_template_phrases(self):
        text = "I am excited to apply for this position. I am writing to express my genuine interest in the role."
        rewritten = reduce_plagiarism_risk(text, context="backend engineering at Acme")

        self.assertNotIn("I am excited to apply for this position", rewritten)
        self.assertIn("Acme", rewritten)
        self.assertGreater(len(rewritten.split()), 3)
