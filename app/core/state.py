from typing import List, Optional, Literal, Dict, Any, TypedDict
from datetime import datetime
from pydantic import BaseModel, Field

# --- Audit Models (Saved to SQLite) ---
class Finding(BaseModel):
    sub_question: str
    source: str          # URL
    excerpt: str         # Exact sentence from the source
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.now)

class JobProfile(BaseModel):
    job_description: str
    resume_text: str
    required_skills: List[str] = []
    company_name: Optional[str] = None

# --- LangGraph State (The "Brain" Memory) ---
class AgentState(TypedDict):
    # Inputs
    jd_text: str
    resume_text: str
    
    # Runtime
    company_name: Optional[str]
    required_skills: List[str]
    tech_stack: List[str]
    current_sub_question: Optional[str]
    iteration: int
    max_iterations: int
    
    # Findings (short-term working memory)
    findings: List[Dict[str, Any]]
    
    # Safety
    tool_call_count: int
    max_tool_calls: int
    
    # Output
    gap_analysis: Optional[str]
    suggested_bullets: List[str]
    final_report: Optional[str]
    status: Literal["pending", "researching", "verifying", "reporting", "done", "failed"]


# --- State for the tailoring/generation workflow ---
class TailoringState(TypedDict):
    job_id: str
    jd_text: str
    company_name: str
    role_title: str

    # Loaded from profile store
    user_profile: Dict[str, Any]

    # Research output
    company_findings: List[Dict[str, Any]]

    # Generated content
    tailored_bullets: List[str]
    cover_letter_text: Optional[str]
    gap_analysis: Optional[str]

    # Output file paths
    resume_docx_path: Optional[str]
    cover_letter_docx_path: Optional[str]

    # LLM provider config (provider, api_key, model, base_url)
    llm_config: Optional[Dict[str, Any]]

    # Runtime
    iteration: int
    max_iterations: int
    status: Literal["running", "done", "failed"]