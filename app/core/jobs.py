import json
import uuid
from datetime import datetime
from pathlib import Path

from app.core.memory import JOB_STATUSES, get_db

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_UPDATABLE = ("company", "role", "jd_text", "app_url", "location", "salary_range", "deadline", "status", "notes")


def _now() -> str:
    return datetime.now().isoformat()


def _add_event(conn, job_id: str, event_type: str, detail: dict | None = None):
    conn.execute(
        "INSERT INTO job_events (job_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
        (job_id, event_type, json.dumps(detail) if detail else None, _now()),
    )


def to_relative_path(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(PROJECT_ROOT))
        except ValueError:
            return str(p)
    return str(p)


def resolve_path(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def create_job(data: dict) -> dict:
    status = data.get("status") or "saved"
    if status not in JOB_STATUSES:
        raise ValueError(f"Invalid status '{status}'")
    job_id = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO jobs (job_id, company, role, jd_text, app_url, location, salary_range,
                                 deadline, status, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, data["company"], data["role"], data.get("jd_text"), data.get("app_url"),
             data.get("location"), data.get("salary_range"), data.get("deadline"), status,
             data.get("notes"), now, now),
        )
        _add_event(conn, job_id, "created", {"status": status})
        conn.commit()
    return get_job(job_id)["job"]


def list_jobs(status: str | None = None) -> list[dict]:
    query = "SELECT * FROM jobs"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY created_at DESC"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_job(job_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        artifacts = [dict(r) for r in conn.execute(
            "SELECT * FROM job_artifacts WHERE job_id = ? ORDER BY id DESC", (job_id,))]
        events = [dict(r) for r in conn.execute(
            "SELECT * FROM job_events WHERE job_id = ? ORDER BY id ASC", (job_id,))]
    return {"job": dict(row), "artifacts": artifacts, "events": events}


def update_job(job_id: str, changes: dict) -> dict | None:
    changes = {k: v for k, v in changes.items() if k in _UPDATABLE}
    if "status" in changes and changes["status"] not in JOB_STATUSES:
        raise ValueError(f"Invalid status '{changes['status']}'")
    for field in ("company", "role"):
        if field in changes and not changes[field]:
            raise ValueError(f"'{field}' cannot be empty")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(
                f"UPDATE jobs SET {sets}, updated_at = ? WHERE job_id = ?",
                (*changes.values(), _now(), job_id),
            )
            if "status" in changes and changes["status"] != row["status"]:
                _add_event(conn, job_id, "status_changed",
                           {"from": row["status"], "to": changes["status"]})
            if "notes" in changes and changes["notes"] != row["notes"]:
                _add_event(conn, job_id, "note_added")
            conn.commit()
    return get_job(job_id)["job"]


def delete_job(job_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM job_artifacts WHERE job_id = ?", (job_id,))
        conn.commit()
        return cur.rowcount > 0


def attach_generation(job_id: str, run_id: str, resume: str | None,
                      cover_letter: str | None, gaps, jd_source: str | None = None) -> None:
    with get_db() as conn:
        now = _now()
        for kind, path in (("resume", resume), ("cover_letter", cover_letter)):
            if path:
                conn.execute(
                    "INSERT INTO job_artifacts (job_id, kind, file_path, created_at) VALUES (?, ?, ?, ?)",
                    (job_id, kind, to_relative_path(path), now),
                )
        conn.execute(
            "INSERT INTO job_artifacts (job_id, kind, content, created_at) VALUES (?, 'analysis', ?, ?)",
            (job_id, json.dumps({"gaps": gaps, "run_id": run_id}), now),
        )
        event_detail = {"run_id": run_id}
        if jd_source:
            event_detail["jd_source"] = jd_source
        _add_event(conn, job_id, "generated", event_detail)
        conn.execute("UPDATE jobs SET updated_at = ? WHERE job_id = ?", (now, job_id))
        conn.commit()


def get_artifact_path(job_id: str, kind: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT file_path FROM job_artifacts WHERE job_id = ? AND kind = ? AND file_path IS NOT NULL "
            "ORDER BY id DESC LIMIT 1", (job_id, kind)).fetchone()
    return row["file_path"] if row else None
