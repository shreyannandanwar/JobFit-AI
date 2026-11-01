from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_setup_profile_rejects_malformed_pdf():
    response = client.post(
        "/setup/profile",
        files={
            "resume": (
                "malformed.pdf",
                b"%PDF-1.4\n%Malformed PDF content",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Unable to read PDF file"}


def test_setup_projects_rejects_short_description():
    import json
    bad_projects = json.dumps([
        {"title": "Valid Project", "description": "Too short", "technologies": ["Python"]}
    ])
    response = client.post("/setup/projects", data={"projects": bad_projects})
    assert response.status_code == 422
    assert "under 30 characters" in response.json()["detail"]


def test_setup_projects_rejects_cross_contaminated_description():
    import json
    corrupted_cms = json.dumps([
        {
            "title": "Portfolio CMS: Self-Hosted Developer Portfolio & Blog Platform",
            "technologies": ["Python", "Flask", "PostgreSQL"],
            "description": "Key Features: Ensemble demand forecasting using Prophet and XGBoost with interactive visualization, SKU-level inventory optimization using the Newsvendor model.",
        }
    ])
    response = client.post("/setup/projects", data={"projects": corrupted_cms})
    assert response.status_code == 422
    assert "mismatched keywords" in response.json()["detail"]


def test_setup_projects_accepts_clean_project():
    import json
    clean_project = json.dumps([
        {
            "title": "Developer Portfolio CMS",
            "technologies": ["Python", "Flask", "PostgreSQL"],
            "description": "Portfolio CMS is a self-hosted platform allowing developers to publish articles and showcase projects.",
        }
    ])
    response = client.post("/setup/projects", data={"projects": clean_project})
    assert response.status_code == 200
    assert response.json()["projects_found"] == 1