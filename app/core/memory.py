import sqlite3
import json
from datetime import datetime
from app.core.state import Finding

DB_PATH = "jobfit_audit.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

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

def update_job_status(job_id: str, status: str, report: str = ""):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO job_results (job_id, status, final_report, created_at) VALUES (?, ?, ?, ?)",
            (job_id, status, report, datetime.now().isoformat())
        )
        conn.commit()