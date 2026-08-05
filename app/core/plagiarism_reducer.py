import re
from typing import Optional


def reduce_plagiarism_risk(text: str, context: Optional[str] = None) -> str:
    """Rewrite common template-style phrases into a more personalized, lower-risk version.

    This is a lightweight heuristic helper rather than a true plagiarism detector.
    It aims to reduce generic phrasing by replacing common openings and overused
    expressions with more context-aware alternatives.
    """
    if not text or not text.strip():
        return ""

    cleaned = re.sub(r"\s+", " ", text.strip())

    replacements = [
        (r"\bI am excited to apply for this position\b", "I am interested in contributing to this opportunity"),
        (r"\bI am writing to express my genuine interest in the role\b", "I am keen to contribute my background to this role"),
        (r"\bI am writing to express my genuine interest in the\s+([A-Za-z0-9 .,-]+) position\b", r"I am interested in contributing to the \1 position"),
        (r"\bThank you for your time and consideration\b", "Thank you for considering my application"),
        (r"\bI would welcome the opportunity to learn more about your roadmap\b", "I would value the chance to discuss your roadmap in more detail"),
    ]

    rewritten = cleaned
    for pattern, replacement in replacements:
        rewritten = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)

    if context and context.strip():
        rewritten = rewritten.replace("this opportunity", f"this opportunity at {context}")
        rewritten = rewritten.replace("this role", f"this role at {context}")

    # Add a subtle personalization cue if the text is still very generic.
    if len(rewritten.split()) < 12 and context:
        rewritten = f"{rewritten} My experience is grounded in practical delivery and measurable outcomes."

    return rewritten
