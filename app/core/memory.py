import os
import sqlite3
import json
from datetime import datetime, timedelta
from app.core.state import Finding

DB_PATH = "jobfit_audit.db"

def get_db(path: str | None = None):
    conn = sqlite3.connect(path or os.environ.get("JOBFIT_DB", DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

JOB_STATUSES = (
    "saved", "preparing", "applied", "assessment", "interview", "offer",
    "rejected", "withdrawn", "archived",
)

_MIGRATIONS = [
    # v1: job tracker
    f"""
    CREATE TABLE IF NOT EXISTS jobs (
        job_id       TEXT PRIMARY KEY,
        company      TEXT NOT NULL,
        role         TEXT NOT NULL,
        jd_text      TEXT,
        app_url      TEXT,
        location     TEXT,
        salary_range TEXT,
        deadline     TEXT,
        status       TEXT NOT NULL DEFAULT 'saved'
                     CHECK (status IN ({", ".join(repr(x) for x in JOB_STATUSES)})),
        notes        TEXT,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS job_events (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id     TEXT NOT NULL,
        event_type TEXT NOT NULL,
        detail     TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS job_artifacts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id     TEXT NOT NULL,
        kind       TEXT NOT NULL,
        file_path  TEXT,
        content    TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id);
    CREATE INDEX IF NOT EXISTS idx_job_artifacts_job ON job_artifacts(job_id);
    """,
    # v2: link generation runs to tracker jobs
    "ALTER TABLE job_results ADD COLUMN tracker_job_id TEXT;",
    # v3: cache of structured JD extractions keyed by JD hash + LLM config
    """
    CREATE TABLE IF NOT EXISTS jd_extractions (
        cache_key  TEXT PRIMARY KEY,
        payload    TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
]


def run_migrations():
    conn = get_db()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(_MIGRATIONS[version:], start=version + 1):
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {i}")
        conn.commit()
    finally:
        conn.close()


def sweep_stale_jobs(max_age_minutes: int = 30) -> int:
    """Mark generation runs stuck in 'processing' (e.g. server restart) as interrupted."""
    cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat()
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE job_results SET status = 'interrupted' WHERE status = 'processing' AND created_at < ?",
            (cutoff,),
        )
        conn.commit()
        return cur.rowcount


def init_db():
    with get_db() as conn:
        # Table for tracking agent decisions
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                sub_question TEXT,
                llm_thought TEXT,
                tool_used TEXT,
                tool_input TEXT,
                tool_output TEXT,
                confidence REAL,
                source_url TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Table for final results
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_results (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                final_report TEXT,
                gap_analysis TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    run_migrations()

def log_step(job_id: str, step_name: str, data: dict):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO audit_log 
               (job_id, step_name, sub_question, llm_thought, tool_used, tool_input, tool_output, confidence, source_url) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, step_name, data.get("sub_question"), data.get("thought"), 
             data.get("tool"), data.get("tool_input"), data.get("tool_output"),
             data.get("confidence"), data.get("source"))
        )
        conn.commit()

def update_job_status(job_id: str, status: str, report: str = "", tracker_job_id: str | None = None):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO job_results (job_id, status, final_report, created_at, tracker_job_id)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET
                 status = excluded.status,
                 final_report = excluded.final_report,
                 tracker_job_id = COALESCE(excluded.tracker_job_id, job_results.tracker_job_id)""",
            (job_id, status, report, datetime.now().isoformat(), tracker_job_id)
        )
        conn.commit()
