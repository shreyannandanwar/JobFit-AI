# Resume section detection

`extract_profile()` in `app/core/profile_parser.py` reads plain text. It strips
blank lines and surrounding whitespace, extracts contact fields and known skills
from the whole text, then assigns section content using the rules below. It does
not interpret PDF layout or Markdown structure.

## Recognized sections

Detection is case-insensitive. After trimming spaces, colons, hyphens, tabs and
vertical bars from both ends, a candidate line must be at most 40 characters.
A whole-word match for any keyword in the following table starts a section;
the line does not have to consist only of that keyword.

| Profile field | Keywords in `SECTION_PATTERNS` | Example headings |
| --- | --- | --- |
| `education` | education, academic, qualification, degree | Education; Academic Background |
| `experience` | experience, employment, work history, professional | Work History; Professional Experience |
| `certifications` | certif, licens, course, training | Training; Course |
| `projects` | projects, portfolio, work samples | Projects; Work Samples |
| `activities` | activities, volunteer, leadership, extracurricular, community | Volunteer; Community Activities |
| `skills` | skills, technologies, tools, competencies, proficiency | Technical Skills; Tools |
| `summary` | summary, objective, about, profile | Summary; About Me |

The regex alternatives are literal words, not stems: for example,
`Certifications`, `Licenses` and `Courses` do not match the current
`certifications` pattern. When a line matches more than one section, the first
matching field in the table wins. A short content line containing a keyword can
also be mistaken for a heading; this is a heuristic, not a semantic classifier.

## How content is assigned

A recognized heading selects the current section and is omitted from its content.
Every subsequent non-heading line belongs to that section until another recognized
heading appears. Repeated headings append to the same field. Content before the
first recognized heading is not assigned to a section, although contact and skill
extraction still examines the full text.

Unrecognized headings do not start a new section: they stay in the current
section as ordinary content. Missing sections have the empty-string value `""`.
The separately extracted `skills` value is initially a list of known skill names;
a recognized Skills heading replaces it with the section's text string.

## Name fallback

Among the first five non-blank lines, `_extract_name()` looks for two to four
capitalized words matching its name regex. If none match, it uses the first
non-blank line, even if that line is a heading. `"Unknown"` is used only when
there are no non-blank lines, such as an empty resume.

## Example

```python
from app.core.profile_parser import extract_profile

resume = """Jane Example
Summary
Builds services.
Education
BSc Computing
Projects
API Monitor
Pings endpoints.
Hobbies
Climbing
Skills
Python, SQL
"""
profile = extract_profile(resume)
```

The relevant fields are:

```python
{
    "name": "Jane Example",
    "summary": "Builds services.",
    "education": "BSc Computing",
    "projects": "API Monitor\nPings endpoints.\nHobbies\nClimbing",
    "skills": "Python, SQL",
    "experience": "",
    "certifications": "",
    "activities": "",
}
```

`Hobbies` is not recognized, so it remains inside `projects`. The project block
parser (`parse_projects_text`) is a separate operation; `extract_profile` keeps
resume section content as text.
