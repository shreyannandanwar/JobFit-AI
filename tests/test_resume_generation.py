import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.nodes import cover_letter_node
from app.core.state import TailoringState


class ResumeGenerationTests(unittest.TestCase):
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
        self.assertGreater(len(result["cover_letter_text"].split()), 25)

    def test_cover_letter_uses_projects_from_profile(self):
        state = TailoringState(
            job_id="demo",
            jd_text="Build backend systems with Python and APIs",
            company_name="Acme",
            role_title="Software Engineer",
            user_profile={
                "name": "Alex Doe",
                "skills": ["python", "api", "docker"],
                "experience": "Built REST APIs for analytics products. Led deployment automation.",
                "project_list": [
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
                ],
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

        result = cover_letter_node(state)

        self.assertIn("Portfolio CMS", result["cover_letter_text"])
        self.assertIn("developer portfolio", result["cover_letter_text"])
