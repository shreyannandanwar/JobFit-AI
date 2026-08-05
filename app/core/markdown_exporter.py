import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List


def _clean_markdown_with_llm(content: str, title: str, llm_cfg: Dict[str, Any] | None = None) -> str:
    """Rewrite markdown into a cleaner structure. Falls back to a deterministic formatter when no LLM is available."""
    if not llm_cfg or not llm_cfg.get("provider"):
        return _deterministic_format_markdown(content, title)

    from app.core.llm import llm_chat

    prompt = (
        f"Rewrite the following markdown content for a professional profile export. "
        f"Keep the meaning intact, improve structure, remove fluff, and preserve headings. "
        f"Return only the rewritten markdown.\n\nTitle: {title}\n\nContent:\n{content}"
    )
    try:
        rewritten = llm_chat(
            [
                {"role": "system", "content": "You are a careful document editor. Rewrite markdown clearly and professionally."},
                {"role": "user", "content": prompt},
            ],
            llm_cfg,
            temperature=0.3,
            max_tokens=1200,
        )
        return rewritten.strip() or _deterministic_format_markdown(content, title)
    except Exception:
        return _deterministic_format_markdown(content, title)


def _deterministic_format_markdown(content: str, title: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        return ""

    lines = [line.rstrip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return ""

    # Normalize bullets and paragraphs.
    normalized: List[str] = []
    for line in lines:
        if line.startswith("- ") or line.startswith("* "):
            normalized.append(line)
        elif normalized and normalized[-1].startswith(("- ", "* ")) and not line.startswith(("#", "##", "**")):
            normalized.append(line)
        else:
            normalized.append(line)

    if title.lower() == "projects":
        return "\n\n".join(normalized)
    return "\n\n".join(normalized)


def _reorganize_markdown_content(content: str, title: str, llm_cfg: Dict[str, Any] | None = None) -> str:
    """Rewrite markdown content into a cleaner, better-organized structure. Uses AI when available; otherwise falls back to deterministic formatting."""
    cleaned = content.strip()
    if not cleaned:
        return ""

    if llm_cfg and llm_cfg.get("provider"):
        from app.core.llm import llm_chat

        prompt = (
            f"Reorganize and rewrite the markdown content below into a cleaner, more professional structure. "
            f"Keep all important facts and meaning intact, improve headings and ordering, and make the file easier to read. "
            f"Do not remove or merge sections. Preserve every project section, bullet, and heading. "
            f"Return only the rewritten markdown.\n\nTitle: {title}\n\nContent:\n{content}"
        )
        try:
            rewritten = llm_chat(
                [
                    {"role": "system", "content": "You are a careful markdown editor. Improve structure and readability without losing facts or sections."},
                    {"role": "user", "content": prompt},
                ],
                llm_cfg,
                temperature=0.2,
                max_tokens=2200,
            )
            if rewritten.strip():
                return rewritten.strip()
        except Exception:
            pass

    return _deterministic_reorganize_markdown(cleaned, title)


def _deterministic_reorganize_markdown(content: str, title: str) -> str:
    """Normalize markdown formatting when AI is unavailable."""
    lines = [line.rstrip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""

    normalized: List[str] = []
    if not lines[0].startswith("#"):
        normalized.append(f"# {title.title()}")
        normalized.append("")

    for line in lines:
        if line.startswith("#"):
            normalized.append(line)
        elif re.match(r"^[-*]\s+", line):
            normalized.append(line)
        else:
            if normalized and normalized[-1] not in {"", "---"} and not normalized[-1].startswith("#") and not re.match(r"^[-*]\s+", normalized[-1]):
                normalized.append(line)
            else:
                normalized.append(line)

    # Collapse extra blank lines and ensure a single blank line between blocks.
    sections: List[str] = []
    current: List[str] = []
    for line in normalized:
        if line == "":
            if current:
                sections.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        sections.append("\n".join(current))

    return "\n\n".join(sections).strip()


def rewrite_markdown_file_with_ai(path: str | os.PathLike[str], llm_cfg: Dict[str, Any] | None = None) -> str:
    """Read a markdown file, rewrite its content with AI, and save the updated version. Returns the rewritten file path."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    title = file_path.stem.replace("_", " ").replace("-", " ").title()
    rewritten = _reorganize_markdown_content(content, title, llm_cfg)

    if rewritten:
        if file_path.name.lower() == "skills.md":
            rewritten = rewritten.rstrip() + "\n\nSee also: projects.json for the full project portfolio.\n"
        file_path.write_text(rewritten + "\n", encoding="utf-8")
    return str(file_path)


def rewrite_markdown_files_with_ai(
    input_dir: str | os.PathLike[str], llm_cfg: Dict[str, Any] | None = None, recursive: bool = True
) -> List[str]:
    """Scan a directory for markdown files and rewrite each one in place. Returns the updated file paths."""
    root = Path(input_dir)
    if not root.exists():
        raise FileNotFoundError(f"Markdown directory not found: {root}")

    pattern = "**/*.md" if recursive else "*.md"
    updated_files: List[str] = []
    for file_path in sorted(root.glob(pattern)):
        if file_path.is_file():
            updated_files.append(rewrite_markdown_file_with_ai(file_path, llm_cfg))
    return updated_files


def export_projects_to_json(
    projects: List[Dict[str, Any]], output_dir: str = "output/profile"
) -> str:
    """Write projects to a JSON file and remove the legacy markdown project export if present."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "projects.json")
    legacy_md_path = os.path.join(output_dir, "projects.md")
    if os.path.exists(legacy_md_path):
        os.remove(legacy_md_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2)
    return path


def export_profile_to_markdown(
    profile: Dict[str, Any], output_dir: str = "output/profile", llm_cfg: Dict[str, Any] | None = None
) -> List[str]:
    """Write one .md file per resume section. Returns list of created paths."""
    os.makedirs(output_dir, exist_ok=True)
    created: List[str] = []

    personal = os.path.join(output_dir, "personal_info.md")
    with open(personal, "w", encoding="utf-8") as f:
        f.write("# Personal Information\n\n")
        for field in ("name", "email", "phone", "linkedin", "github"):
            value = profile.get(field, "")
            if value:
                f.write(f"- **{field.title()}:** {value}\n")
        f.write("\n")
    created.append(personal)

    for section in ("summary", "education", "experience", "certifications", "activities"):
        content = profile.get(section, "").strip()
        if not content:
            continue
        path = os.path.join(output_dir, f"{section}.md")
        cleaned = _clean_markdown_with_llm(content, section.title(), llm_cfg)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {section.title()}\n\n{cleaned}\n")
        created.append(path)

    skills: List[str] = profile.get("skills", [])
    if skills:
        path = os.path.join(output_dir, "skills.md")
        cleaned = _clean_markdown_with_llm("\n".join(f"- {skill}" for skill in skills), "Skills", llm_cfg)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Skills\n\n")
            f.write(cleaned + "\n")
            f.write("\nSee also: projects.json for the full project portfolio.\n")
        created.append(path)

    # Write projects.json if structured projects were parsed from the resume
    project_list: List[Dict[str, Any]] = profile.get("project_list", [])
    if project_list:
        created.append(export_projects_to_json(project_list, output_dir))

    return created


def export_projects_to_markdown(
    projects: List[Dict[str, Any]], output_dir: str = "output/profile", llm_cfg: Dict[str, Any] | None = None
) -> str:
    """Write all projects to a single projects.md using a standardized structure."""
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "projects.md")

    content_parts: List[str] = []
    for idx, project in enumerate(projects, start=1):
        title = project.get("title", f"Project {idx}").strip()
        description = (project.get("description") or "").strip()
        github = (project.get("github") or "").strip()
        deployment = (project.get("deployment") or "").strip()
        techs = [t.strip() for t in project.get("technologies", []) if t and t.strip()]
        key_features = [t.strip() for t in project.get("key_features", []) if t and t.strip()]
        why = (project.get("why") or "").strip()
        problem = (project.get("problem") or "").strip()
        unique_items = [t.strip() for t in project.get("unique", []) if t and t.strip()]
        technical_explanation = [t.strip() for t in project.get("technical_explanation", []) if t and t.strip()]

        if content_parts:
            content_parts.append("")
        content_parts.append(f"# {title}")
        content_parts.append("")
        content_parts.append("## Links")
        content_parts.append("")
        if github:
            content_parts.append(f"- GitHub: {github}")
        if deployment:
            content_parts.append(f"- Demo: {deployment}")
        if not github and not deployment:
            content_parts.append("- No links provided")
        content_parts.append("")
        content_parts.append("## Description")
        content_parts.append("")
        content_parts.append(description or "No description provided.")
        content_parts.append("")
        content_parts.append("## Key Features")
        content_parts.append("")
        if key_features:
            content_parts.extend(f"- {feature}" for feature in key_features)
        elif description:
            content_parts.extend([
                "- Built a solution that demonstrates strong product and engineering thinking",
                "- Applied modern tools and workflows to deliver practical value",
                "- Focused on usability, reliability, or measurable impact",
            ])
        else:
            content_parts.extend(["- Feature 1", "- Feature 2", "- Feature 3"])
        content_parts.append("")
        content_parts.append("## Why?")
        content_parts.append("")
        content_parts.append(why or "This project was built to solve a real problem and demonstrate meaningful technical and product impact.")
        content_parts.append("")
        content_parts.append("## What Problem Does It Solve?")
        content_parts.append("")
        content_parts.append(problem or "It addresses a practical need by simplifying workflows, improving user experience, or automating a repetitive task.")
        content_parts.append("")
        content_parts.append("## Why Is This Project Unique?")
        content_parts.append("")
        if unique_items:
            content_parts.extend(f"- {item}" for item in unique_items)
        else:
            content_parts.extend([
                "- It combines a clear product goal with strong engineering execution",
                "- It shows thoughtful design and implementation choices",
                "- It demonstrates adaptability across real-world constraints",
            ])
        content_parts.append("")
        content_parts.append("## Technical Explanation")
        content_parts.append("")
        if technical_explanation:
            content_parts.extend(f"- {item}" for item in technical_explanation)
        else:
            content_parts.extend([
                "- The architecture was chosen to balance scalability, maintainability, and speed of delivery",
                "- The implementation highlights practical tradeoffs and modern engineering practices",
                "- The solution is structured to be understandable, extensible, and production-ready",
            ])
        content_parts.append("")
        content_parts.append("## Tech Stack")
        content_parts.append("")
        if techs:
            content_parts.extend(f"- {tech}" for tech in techs)
        else:
            content_parts.append("- Not specified")

    cleaned = _clean_markdown_with_llm("\n".join(content_parts), "Projects", llm_cfg)
    with open(path, "w", encoding="utf-8") as f:
        f.write(cleaned + "\n")
    return path
