import json
import tempfile
import unittest
from pathlib import Path

from app.core.markdown_exporter import export_projects_to_json
from app.core.profile_parser import parse_projects_text


class ProjectParserTests(unittest.TestCase):
    def test_duplicate_project_titles_keep_first_and_preserve_distinct_projects(self):
        for duplicate_title in ("Task Tracker", "task tracker", "TASK TRACKER"):
            with self.subTest(duplicate_title=duplicate_title):
                text = f"""## Project Title: Task Tracker
Description: The original task manager.
Tech: Python, FastAPI

## Project Title: {duplicate_title}
Description: A duplicate that should not replace the original.
Tech: React

## Project Title: Analytics Dashboard
Description: A distinct project.
Tech: JavaScript
"""
                projects = parse_projects_text(text)

                self.assertEqual([p["title"] for p in projects],
                                 ["Task Tracker", "Analytics Dashboard"])
                self.assertEqual(sum(p["title"].lower() == "task tracker" for p in projects), 1)
                self.assertEqual(projects[0]["description"],
                                 "Description: The original task manager.")
                self.assertEqual(projects[0]["technologies"], ["Python", "FastAPI"])
                self.assertEqual(projects[1]["technologies"], ["JavaScript"])

    def test_export_projects_to_json_file(self):
        projects = [{"title": "Sample Project", "description": "A sample project", "technologies": ["Python"]}]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = export_projects_to_json(projects, output_dir=tmpdir)
            saved_path = Path(output_path)

            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.name, "projects.json")
            data = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(data[0]["title"], "Sample Project")
            self.assertEqual(data[0]["description"], "A sample project")

    def test_parses_multiple_project_sections_from_plain_text(self):
        text = """Project 1
A simple app for task tracking.
Tech: Python, FastAPI

Project 2
A dashboard for analytics.
Tech: React, Node.js

Project 3
A recommendation system.
Tech: PyTorch, Flask
"""

        projects = parse_projects_text(text)

        self.assertEqual(len(projects), 3)
        self.assertEqual([p["title"] for p in projects], ["Project 1", "Project 2", "Project 3"])

    def test_parses_project_title_markers_from_uploaded_doc_style_text(self):
        text = """## Project Title: Telco Customer Churn Prediction & Retention System
Github: https://example.com/project1
Description: Predicts churn for telecom customers.

## Project Title: Predictive Inventory Advisor
Github: https://example.com/project2
Description: Helps optimize inventory.

## Project Title: Agent Swarp
Github: https://example.com/project3
Description: An AI research assistant.

## Project Title: Portfolio CMS
Github: https://example.com/project4
Description: A developer portfolio CMS.

## Project Title: Code Intelligence Engine
Github: https://example.com/project5
Description: A code intelligence tool.

## Project Title: Data Pipeline Studio
Github: https://example.com/project6
Description: A data pipeline orchestration tool.
"""

        projects = parse_projects_text(text)

        self.assertEqual(len(projects), 6)
        self.assertEqual(projects[0]["title"], "Telco Customer Churn Prediction & Retention System")
        self.assertEqual(projects[-1]["title"], "Data Pipeline Studio")


if __name__ == "__main__":
    unittest.main()
