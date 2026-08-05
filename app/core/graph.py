from langgraph.graph import StateGraph, END
from app.core.state import AgentState, TailoringState

from app.core.nodes import (
    planner_node, researcher_node, verifier_node, reporter_node,
    profile_loader_node, company_researcher_node,
    resume_tailor_node, cover_letter_node, docx_export_node,
)

# --- Gap-analysis graph (original) ---
builder = StateGraph(AgentState)

# Add nodes
builder.add_node("planner", planner_node)       # Extracts skills & company
builder.add_node("researcher", researcher_node) # Searches web for tech stack
builder.add_node("verifier", verifier_node)     # Checks if sources are valid
builder.add_node("reporter", reporter_node)     # Compares resume vs JD

# Define edges
builder.set_entry_point("planner")

# After planning, go to research
builder.add_edge("planner", "researcher")
# After research, verify
builder.add_edge("researcher", "verifier")

# After research, verify. If confidence < 0.5, go back to research (reformulate query)
builder.add_conditional_edges(
    "verifier",
    lambda state: "researcher" if state["iteration"] < state["max_iterations"] and len(state["tech_stack"]) == 0 else "reporter",
    {
        "researcher": "researcher",
        "reporter": "reporter"
    }
)

builder.add_edge("reporter", END)

# Compile the graph
agent_graph = builder.compile()


# --- Tailoring / document-generation graph ---
tailor_builder = StateGraph(TailoringState)

tailor_builder.add_node("load_profile", profile_loader_node)
tailor_builder.add_node("research_company", company_researcher_node)
tailor_builder.add_node("tailor_resume", resume_tailor_node)
tailor_builder.add_node("write_cover_letter", cover_letter_node)
tailor_builder.add_node("export_docx", docx_export_node)

tailor_builder.set_entry_point("load_profile")
tailor_builder.add_edge("load_profile", "research_company")
tailor_builder.add_edge("research_company", "tailor_resume")
tailor_builder.add_edge("tailor_resume", "write_cover_letter")
tailor_builder.add_edge("write_cover_letter", "export_docx")
tailor_builder.add_edge("export_docx", END)

tailoring_graph = tailor_builder.compile()