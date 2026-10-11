from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.state import JobRecord


def test_valid_job_record():
    job = JobRecord(company="Google", role="AI Engineer")

    assert job.company == "Google"
    assert job.role == "AI Engineer"
    assert job.status == "saved"


def test_optional_fields_default_to_none():
    job = JobRecord(company="Google", role="AI Engineer")

    assert job.job_description is None
    assert job.location is None


def test_optional_fields_accept_values():
    job = JobRecord(
        company="Google",
        role="AI Engineer",
        job_description="Build AI applications",
        location="Bengaluru",
    )

    assert job.job_description == "Build AI applications"
    assert job.location == "Bengaluru"


def test_creation_timestamp_is_generated():
    job = JobRecord(company="Google", role="AI Engineer")

    assert isinstance(job.created_at, datetime)


def test_each_record_gets_its_own_timestamp():
    first = JobRecord(company="Google", role="AI Engineer")
    second = JobRecord(company="Microsoft", role="ML Engineer")

    assert first.created_at is not second.created_at


@pytest.mark.parametrize("field", ["company", "role"])
@pytest.mark.parametrize("value", ["", "   "])
def test_rejects_empty_required_fields(field, value):
    data = {"company": "Google", "role": "AI Engineer"}
    data[field] = value

    with pytest.raises(ValidationError):
        JobRecord(**data)


@pytest.mark.parametrize("field", ["company", "role"])
def test_rejects_missing_required_fields(field):
    data = {"company": "Google", "role": "AI Engineer"}
    del data[field]

    with pytest.raises(ValidationError):
        JobRecord(**data)


@pytest.mark.parametrize(
    "status",
    [
        "saved",
        "preparing",
        "applied",
        "interview",
        "offer",
        "rejected",
        "withdrawn",
    ],
)
def test_accepts_valid_statuses(status):
    job = JobRecord(
        company="Google",
        role="AI Engineer",
        status=status,
    )

    assert job.status == status


def test_rejects_invalid_status():
    with pytest.raises(ValidationError):
        JobRecord(
            company="Google",
            role="AI Engineer",
            status="pending",
        )