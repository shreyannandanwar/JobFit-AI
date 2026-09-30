import json
import os
import sys
from pathlib import Path

# Add the project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.graph import agent_graph
from app.core.memory import init_db
import uuid

# Sample test cases (Update these with real JDs or keep them as placeholders)
TEST_CASES = [
    {
        "id": "test_1",
        "job_description": "Software Engineer at Acme Corp. Must know Python, AWS, and Docker.",
        "resume_text": "Experienced Python developer with 5 years of AWS and Kubernetes.",
        "expected_skills": ["Python", "AWS", "Docker"]
    },
    {
        "id": "test_2",
        "job_description": "Data Scientist at Beta Inc. Must know SQL, Machine Learning, and Tableau.",
        "resume_text": "Data analyst with SQL and Excel skills. Basic Python.",
        "expected_skills": ["SQL", "Machine Learning", "Tableau"]
    },
    {
        "id": "test_3",
        "job_description": "Frontend Engineer at Gamma LLC. Must know React, TypeScript, and CSS.",
        "resume_text": "Full-stack dev with React and JavaScript.",
        "expected_skills": ["React", "TypeScript", "CSS"]
    }
]

def run_harness():
    init_db()  # Ensure DB exists
    
    results = []
    for test in TEST_CASES:
        job_id = f"harness_{test['id']}"
        print(f"\n🧪 Running test: {test['id']}...")
        
        # Initial state
        state = {
            "job_id": job_id,
            "jd_text": test["job_description"],
            "resume_text": test["resume_text"],
            "company_name": None,
            "required_skills": [],
            "tech_stack": [],
            "findings": [],
            "current_sub_question": None,
            "iteration": 0,
            "max_iterations": 4,
            "tool_call_count": 0,
            "max_tool_calls": 10,
            "gap_analysis": None,
            "suggested_bullets": [],
            "final_report": None,
            "status": "researching"
        }
        
        try:
            final_state = agent_graph.invoke(state)
            findings = final_state.get("findings", [])
            
            # Scoring
            extracted_skills = []
            for f in findings:
                for skill in test["expected_skills"]:
                    if skill.lower() in f.get("excerpt", "").lower():
                        extracted_skills.append(skill)
            
            unique_extracted = list(set(extracted_skills))
            
            # Completeness: % of required skills found in excerpts
            completeness = len(unique_extracted) / max(1, len(test["expected_skills"]))
            
            # Grounding: % of findings with a valid source URL
            grounded = sum(1 for f in findings if f.get("source") and "fallback" not in f["source"])
            grounding = grounded / max(1, len(findings))
            
            # Efficiency: Tool call count
            tool_calls = final_state.get("tool_call_count", 0)
            
            results.append({
                "test_id": test["id"],
                "completeness": completeness,
                "grounding": grounding,
                "tool_calls": tool_calls,
                "status": "success"
            })
            
            print(f"   ✅ Completeness: {completeness:.2f}, Grounding: {grounding:.2f}, Calls: {tool_calls}")
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results.append({"test_id": test["id"], "status": "failed", "error": str(e)})
    
    # Summary
    print("\n" + "="*50)
    print("📊 HARNESS SUMMARY")
    print("="*50)
    successful = [r for r in results if r.get("status") == "success"]
    if successful:
        avg_comp = sum(r["completeness"] for r in successful) / len(successful)
        avg_ground = sum(r["grounding"] for r in successful) / len(successful)
        avg_calls = sum(r["tool_calls"] for r in successful) / len(successful)
        print(f"Average Completeness: {avg_comp:.2f}")
        print(f"Average Grounding: {avg_ground:.2f}")
        print(f"Average Tool Calls: {avg_calls:.2f}")
    else:
        print("No successful tests to evaluate.")
    
    # Save results
    with open("eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("Results saved to eval_results.json")

if __name__ == "__main__":
    run_harness()