import os
from langchain_openai import ChatOpenAI
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from typing import List

# Initialize LLM (Works with OpenAI, OpenRouter, or Local via vLLM)
LLM = ChatOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    api_key=os.getenv("OPENAI_API_KEY"),
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    temperature=0.1,
    timeout=60,
)

# --- Pydantic Schemas for Structured Output ---

class PlanningOutput(BaseModel):
    company_name: str = Field(description="The name of the company hiring.")
    required_skills: List[str] = Field(description="Hard technical skills explicitly listed in the JD (e.g., Python, AWS, Kubernetes).")
    research_questions: List[str] = Field(description="List of specific sub-questions to research, e.g., 'What is the tech stack of Acme Corp?'.")

class ResearchFinding(BaseModel):
    sub_question: str = Field(description="The sub-question being answered.")
    source: str = Field(description="The URL of the source.")
    excerpt: str = Field(description="A direct quote from the source that answers the question.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that this source is accurate and relevant.")

class GapAnalysisOutput(BaseModel):
    gaps: List[str] = Field(description="Skills from the JD that are missing from the user's resume.")
    suggested_bullets: List[str] = Field(description="3-5 tailored bullet points the user should add to their resume to bridge the gap.")
    overall_score: float = Field(ge=0.0, le=1.0, description="Match percentage (0-1) between JD and resume.")