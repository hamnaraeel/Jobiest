"""Renders structured CV content into a controlled LaTeX template and
compiles it to PDF. The LLM never generates LaTeX -- it only ever produced
the CVContent structured data (in cv_customization_service); everything
here is plain Python string-building with mandatory escaping, plus a
subprocess call to pdflatex. No LLM output is ever passed to a shell.
"""

import dataclasses
import logging
import re
import subprocess
from pathlib import Path

from app.config import get_settings
from app.schemas.cv import CVContent

logger = logging.getLogger("app.cv_render")

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "cv_templates"

_ESCAPE_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


class LaTeXCompilationError(RuntimeError):
    def __init__(self, message: str, log_excerpt: str = ""):
        super().__init__(message)
        self.log_excerpt = log_excerpt


class PathSecurityError(ValueError):
    pass


def escape_latex(text: str | None) -> str:
    """Escapes LaTeX special characters in a single pass over the
    *original* characters. Sequential `.replace()` calls would corrupt the
    output here -- e.g. escaping backslash first introduces `{` and `}`
    characters, which a later `.replace("{", ...)` pass would then
    re-escape a second time. Building the result character-by-character
    from the input avoids ever re-scanning already-substituted text."""

    if not text:
        return ""
    return "".join(_ESCAPE_CHARS.get(ch, ch) for ch in text)


def _bullets_to_latex(bullets) -> str:
    if not bullets:
        return ""
    items = "\n".join(f"  \\item {escape_latex(b.text)}" for b in bullets)
    return f"\\begin{{itemize}}\n{items}\n\\end{{itemize}}"


def _format_month_year(d) -> str:
    return d.strftime("%b %Y") if d else ""


def _date_range(start, end, currently_working: bool = False) -> str:
    if not start and not end and not currently_working:
        return ""
    end_label = "Present" if currently_working else _format_month_year(end)
    return escape_latex(f"{_format_month_year(start)} -- {end_label}".strip(" -"))


def render_summary_section(summary: str) -> str:
    if not summary:
        return ""
    return f"\\sectiontitle{{Summary}}\n{escape_latex(summary)}\n"


def render_skills_section(skills) -> str:
    if not skills:
        return ""
    lines = []
    for cat in skills:
        if not cat.skills:
            continue
        names = ", ".join(escape_latex(s) for s in cat.skills)
        lines.append(f"\\noindent\\textbf{{{escape_latex(cat.category)}:}} {names}\\\\")
    if not lines:
        return ""
    return "\\sectiontitle{Skills}\n" + "\n".join(lines) + "\n"


def render_experience_section(experience) -> str:
    if not experience:
        return ""
    blocks = []
    for e in experience:
        header = f"\\noindent\\textbf{{{escape_latex(e.role)}}}, {escape_latex(e.company)} \\hfill {_date_range(e.start_date, e.end_date, e.currently_working)}\\\\"
        location = f"\\textit{{{escape_latex(e.location)}}}\\\\" if e.location else ""
        blocks.append(header + ("\n" + location if location else "") + "\n" + _bullets_to_latex(e.bullets))
    return "\\sectiontitle{Experience}\n" + "\n\\vspace{4pt}\n".join(blocks) + "\n"


def render_projects_section(projects) -> str:
    if not projects:
        return ""
    blocks = []
    for p in projects:
        tech = f" \\textit{{({escape_latex(', '.join(p.technologies))})}}" if p.technologies else ""
        header = f"\\noindent\\textbf{{{escape_latex(p.name)}}}{tech}\\\\"
        blocks.append(header + "\n" + _bullets_to_latex(p.bullets))
    return "\\sectiontitle{Projects}\n" + "\n\\vspace{4pt}\n".join(blocks) + "\n"


def render_research_section(research) -> str:
    if not research:
        return ""
    blocks = []
    for r in research:
        tech = f" \\textit{{({escape_latex(', '.join(r.technologies))})}}" if r.technologies else ""
        header = f"\\noindent\\textbf{{{escape_latex(r.title)}}}{tech}\\\\"
        body = f"{escape_latex(r.description)}\\\\" if r.description else ""
        blocks.append(header + ("\n" + body if body else ""))
    return "\\sectiontitle{Research}\n" + "\n\\vspace{4pt}\n".join(blocks) + "\n"


def render_education_section(education) -> str:
    if not education:
        return ""
    blocks = []
    for e in education:
        field = f", {escape_latex(e.field)}" if e.field else ""
        header = f"\\noindent\\textbf{{{escape_latex(e.degree)}{field}}}, {escape_latex(e.institution)} \\hfill {_date_range(e.start_date, e.end_date)}\\\\"
        blocks.append(header)
    return "\\sectiontitle{Education}\n" + "\n".join(blocks) + "\n"


def render_certifications_section(certifications) -> str:
    if not certifications:
        return ""
    items = "\n".join(
        f"  \\item {escape_latex(c.name)}, {escape_latex(c.issuer)}" for c in certifications
    )
    return f"\\sectiontitle{{Certifications}}\n\\begin{{itemize}}\n{items}\n\\end{{itemize}}\n"


def render_achievements_section(achievements) -> str:
    if not achievements:
        return ""
    items = []
    for a in achievements:
        metric = f" ({escape_latex(a.metric)})" if a.metric else ""
        items.append(f"  \\item {escape_latex(a.title)}{metric}")
    return "\\sectiontitle{Achievements}\n\\begin{itemize}\n" + "\n".join(items) + "\n\\end{itemize}\n"


_SECTION_RENDERERS = {
    "summary": lambda c: render_summary_section(c.summary),
    "skills": lambda c: render_skills_section(c.skills),
    "experience": lambda c: render_experience_section(c.experience),
    "projects": lambda c: render_projects_section(c.projects),
    "research": lambda c: render_research_section(c.research),
    "education": lambda c: render_education_section(c.education),
    "certifications": lambda c: render_certifications_section(c.certifications),
    "achievements": lambda c: render_achievements_section(c.achievements),
}


def render_cv_to_latex(content: CVContent, template_name: str = "ats/ml_engineer") -> str:
    template_path = (TEMPLATES_DIR / f"{template_name}.tex").resolve()
    if TEMPLATES_DIR.resolve() not in template_path.parents:
        raise PathSecurityError(f"Template path escapes cv_templates/: {template_name}")
    if not template_path.exists():
        raise FileNotFoundError(f"No such CV template: {template_name}")

    template = template_path.read_text(encoding="utf-8")

    contact_parts = [
        p for p in [
            content.header.email,
            content.header.phone,
            content.header.linkedin,
            content.header.github,
            content.header.portfolio,
            content.header.location,
        ] if p
    ]
    contact_line = " \\quad|\\quad ".join(escape_latex(p) for p in contact_parts)

    order = content.section_order or list(_SECTION_RENDERERS.keys())
    body = "\n".join(_SECTION_RENDERERS[s.value](content) for s in order if s.value in _SECTION_RENDERERS)

    return (
        template
        .replace("{{NAME}}", escape_latex(content.header.name))
        .replace("{{CONTACT_LINE}}", contact_line)
        .replace("{{BODY}}", body)
    )


@dataclasses.dataclass
class CompileResult:
    success: bool
    pdf_path: str | None = None
    error: str | None = None
    log_excerpt: str | None = None


def _resolve_storage_path(job_id: int, filename: str) -> Path:
    base = (Path(__file__).resolve().parents[3] / "backend" / get_settings().cv_storage_dir).resolve()
    job_dir = (base / f"job_{job_id}").resolve()
    if base not in job_dir.parents and job_dir != base:
        raise PathSecurityError("Resolved CV storage path escapes the configured storage directory.")
    target = (job_dir / filename).resolve()
    if job_dir not in target.parents:
        raise PathSecurityError("Resolved CV file path escapes the job's storage directory.")
    return target


def compile_pdf(latex_source: str, job_id: int, version_number: int) -> CompileResult:
    settings = get_settings()
    tex_path = _resolve_storage_path(job_id, f"cv_v{version_number}.tex")
    pdf_path = _resolve_storage_path(job_id, f"cv_v{version_number}.pdf")
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(latex_source, encoding="utf-8")

    try:
        result = subprocess.run(
            [settings.pdflatex_path, "-interaction=nonstopmode", "-halt-on-error",
             "-output-directory", str(tex_path.parent), str(tex_path)],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return CompileResult(success=False, error=f"'{settings.pdflatex_path}' is not installed or not on PATH.")
    except subprocess.TimeoutExpired:
        return CompileResult(success=False, error="pdflatex timed out after 60 seconds.")

    if result.returncode != 0 or not pdf_path.exists():
        log_excerpt = "\n".join(result.stdout.splitlines()[-30:])
        return CompileResult(success=False, error="pdflatex compilation failed.", log_excerpt=log_excerpt)

    if pdf_path.stat().st_size == 0:
        return CompileResult(success=False, error="pdflatex produced an empty PDF file.")

    for ext in (".aux", ".log", ".out"):
        (tex_path.parent / f"cv_v{version_number}{ext}").unlink(missing_ok=True)

    return CompileResult(success=True, pdf_path=str(pdf_path))


def extract_pdf_text(pdf_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def count_pdf_pages(pdf_path: str) -> int:
    from pypdf import PdfReader

    return len(PdfReader(pdf_path).pages)
