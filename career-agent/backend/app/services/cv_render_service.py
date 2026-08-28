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
    # Invisible/exotic Unicode spacing characters that AI-generated text
    # occasionally contains (e.g. a narrow no-break space before a "%")
    # -- plain pdflatex's default font encoding has no glyph for these
    # and fatally errors ("Unicode character ... not set up for use with
    # LaTeX"). Collapsing them to a plain space changes no visible
    # content, only makes the exact same text renderable.
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    "​": "",
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
    return f"\\begin{{tightlist}}\n{items}\n\\end{{tightlist}}"


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
    return "\\sectiontitle{Technical Skills}\n" + "\n".join(lines) + "\n"


def render_experience_section(experience) -> str:
    if not experience:
        return ""
    blocks = []
    for e in experience:
        # Two-line header, matching the master resume: company (bold) with
        # its location right-aligned on the first line, then role
        # (italic) with the date range right-aligned on the second --
        # not the single "Role, Company -- Location [date]" line used in
        # earlier drafts of this template.
        row1 = f"\\tworow{{\\textbf{{{escape_latex(e.company)}}}}}{{{escape_latex(e.location) if e.location else ''}}}"
        date_range = _date_range(e.start_date, e.end_date, e.currently_working)
        row2 = f"\\tworow{{\\textit{{{escape_latex(e.role)}}}}}{{{date_range}}}"
        header = row1 + "\\rowbreak\n" + row2 + "\\rowbreak\n"
        blocks.append(header + _bullets_to_latex(e.bullets))
    return "\\sectiontitle{Work Experience}\n" + "\n\\vspace{8pt}\n".join(blocks) + "\n"


def _clean_project_url(url: str | None) -> str | None:
    """Only ever renders a real link. Resume import occasionally stores
    parsed-anchor placeholder text (e.g. the literal word "GitHub", not a
    URL) in this field -- rendering that as \\href would produce a link
    that goes nowhere, which is worse than omitting it."""
    if not url:
        return None
    url = url.strip()
    if url.lower().startswith(("http://", "https://")):
        return url
    if "." in url and " " not in url:
        return f"https://{url}"
    return None


def _short_link_label(url: str) -> str:
    """"https://linkedin.com/in/hamnaraeel" -> "linkedin/hamnaraeel" --
    matches the master resume's shortened link display text. The full
    URL is always still what \\href actually points to; this only
    changes what's printed."""
    u = url.strip()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
            break
    if u.startswith("www."):
        u = u[4:]
    u = u.rstrip("/")
    parts = u.split("/")
    domain = parts[0].split(".")[0]
    handle = parts[-1] if len(parts) > 1 else ""
    return f"{domain}/{handle}" if handle else domain


def _project_links(p) -> str:
    parts = []
    github = _clean_project_url(getattr(p, "github_url", None))
    if github:
        parts.append(f"\\href{{{github}}}{{GitHub}}")
    demo = _clean_project_url(getattr(p, "demo_url", None))
    if demo:
        parts.append(f"\\href{{{demo}}}{{Live Demo}}")
    return " | ".join(parts)


def render_projects_section(projects) -> str:
    if not projects:
        return ""
    # Each project category (e.g. "Research & ML", "Engineering &
    # Full-Stack") is its own full section heading, "<category>
    # Projects" -- matching the master resume, which treats project
    # categories as top-level sections rather than subheadings nested
    # under one "Projects" section. A project's category was assigned
    # deterministically from its own recorded skill tags, not by the job
    # being applied to (see cv_customization_service._project_category),
    # so grouping is stable across every generation.
    categories: dict[str, list] = {}
    for p in projects:
        categories.setdefault(p.category, []).append(p)

    def _project_block(p) -> str:
        # Title (bold) with GitHub/Live Demo links right-aligned, same
        # \tworow row style as Experience/Education headers, then bullets.
        header = f"\\tworow{{\\textbf{{{escape_latex(p.name)}}}}}{{{_project_links(p)}}}\\rowbreak\n"
        return header + _bullets_to_latex(p.bullets)

    # ~8pt between one project's last bullet and the next project's title.
    parts = []
    for category, items in categories.items():
        parts.append(f"\\sectiontitle{{{escape_latex(category)} Projects}}")
        parts.append("\n\\vspace{8pt}\n".join(_project_block(p) for p in items))
    return "\n".join(parts) + "\n"


def render_research_section(research) -> str:
    if not research:
        return ""
    blocks = []
    for r in research:
        tech = f" \\textit{{({escape_latex(', '.join(r.technologies))})}}" if r.technologies else ""
        header = f"\\noindent\\textbf{{{escape_latex(r.title)}}}{tech}\\\\[3pt]\\nopagebreak[3]"
        body = f"{escape_latex(r.description)}\\\\" if r.description else ""
        blocks.append(header + ("\n" + body if body else ""))
    return "\\sectiontitle{Research}\n" + "\n\\vspace{8pt}\n".join(blocks) + "\n"


def render_education_section(education) -> str:
    if not education:
        return ""
    blocks = []
    for e in education:
        # Two-line header matching Experience/Projects: institution
        # (bold) with its location -- Education has no stored location
        # field, so that side is intentionally left blank rather than
        # showing something unreal -- then degree/field (italic) with
        # the date range right-aligned.
        row1 = f"\\tworow{{\\textbf{{{escape_latex(e.institution)}}}}}{{}}"
        field = f", {escape_latex(e.field)}" if e.field else ""
        date_range = _date_range(e.start_date, e.end_date)
        row2 = f"\\tworow{{\\textit{{{escape_latex(e.degree)}{field}}}}}{{{date_range}}}"
        blocks.append(row1 + "\\rowbreak\n" + row2)
    # 3-5pt between education entries when there's more than one.
    return "\\sectiontitle{Education}\n" + "\n\\vspace{3pt}\n".join(blocks) + "\n"


def render_certifications_section(certifications) -> str:
    if not certifications:
        return ""
    items = "\n".join(
        f"  \\item {escape_latex(c.name)} -- \\textbf{{{escape_latex(c.issuer)}}}" for c in certifications
    )
    return f"\\sectiontitle{{Certifications \\& Trainings}}\n\\begin{{tightlistzero}}\n{items}\n\\end{{tightlistzero}}\n"


def render_achievements_section(achievements) -> str:
    if not achievements:
        return ""
    items = []
    for a in achievements:
        metric = f" ({escape_latex(a.metric)})" if a.metric else ""
        items.append(f"  \\item {escape_latex(a.title)}{metric}")
    return "\\sectiontitle{Achievements}\n\\begin{tightlist}\n" + "\n".join(items) + "\n\\end{tightlist}\n"


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

    # Two contact lines, not one: location/phone (how to reach the
    # candidate directly) on the first, email/LinkedIn/GitHub/portfolio
    # (online presence) on the second. Links use their short display
    # form ("linkedin/handle") like the master resume, while still
    # pointing \href at the real, full stored URL.
    line1_parts = [p for p in [content.header.location, content.header.phone] if p]
    contact_line_1 = " \\quad|\\quad ".join(escape_latex(p) for p in line1_parts)

    line2_items = []
    if content.header.email:
        line2_items.append(escape_latex(content.header.email))
    for url in (content.header.linkedin, content.header.github, content.header.portfolio):
        if url:
            line2_items.append(f"\\href{{{url}}}{{{escape_latex(_short_link_label(url))}}}")
    contact_line_2 = " \\quad|\\quad ".join(line2_items)

    # Built line-by-line and joined with \\ rather than templated with a
    # fixed number of \\[Npt] separators -- a blank line (e.g. no tagline)
    # followed by \\ is a LaTeX error ("There's no line here to end"),
    # not just a cosmetic gap, so an empty line must be skipped entirely
    # rather than rendered blank. Name at 24pt, matching the master
    # resume's much larger header than a typical compact ATS template.
    header_lines = [f"{{\\fontsize{{24}}{{28}}\\selectfont\\bfseries {escape_latex(content.header.name)}}}"]
    if content.header.tagline:
        header_lines.append(escape_latex(content.header.tagline))
    if contact_line_1:
        header_lines.append(contact_line_1)
    if contact_line_2:
        header_lines.append(contact_line_2)
    header_block = "\\\\[2pt]\n".join(header_lines)

    order = content.section_order or list(_SECTION_RENDERERS.keys())
    body = "\n".join(_SECTION_RENDERERS[s.value](content) for s in order if s.value in _SECTION_RENDERERS)

    return (
        template
        .replace("{{HEADER_BLOCK}}", header_block)
        .replace("{{BODY}}", body)
    )


@dataclasses.dataclass
class CompileResult:
    success: bool
    pdf_path: str | None = None
    error: str | None = None
    log_excerpt: str | None = None


def _resolve_storage_path(base_dir_setting: str, subdir: str, filename: str) -> Path:
    base = (Path(__file__).resolve().parents[3] / "backend" / base_dir_setting).resolve()
    target_dir = (base / subdir).resolve()
    if base not in target_dir.parents and target_dir != base:
        raise PathSecurityError("Resolved storage path escapes the configured storage directory.")
    target = (target_dir / filename).resolve()
    if target_dir not in target.parents:
        raise PathSecurityError("Resolved file path escapes its storage directory.")
    return target


def compile_latex_to_pdf(latex_source: str, base_dir_setting: str, subdir: str, filename_stem: str) -> CompileResult:
    """Generic controlled LaTeX -> PDF compilation, used by both CV
    generation (Step 3) and cover letter generation (Step 4) so the
    compile/validate/cleanup logic exists exactly once."""

    settings = get_settings()
    tex_path = _resolve_storage_path(base_dir_setting, subdir, f"{filename_stem}.tex")
    pdf_path = _resolve_storage_path(base_dir_setting, subdir, f"{filename_stem}.pdf")
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
        (tex_path.parent / f"{filename_stem}{ext}").unlink(missing_ok=True)

    return CompileResult(success=True, pdf_path=str(pdf_path))


def compile_pdf(latex_source: str, job_id: int, version_number: int) -> CompileResult:
    settings = get_settings()
    return compile_latex_to_pdf(latex_source, settings.cv_storage_dir, f"job_{job_id}", f"cv_v{version_number}")


def extract_pdf_text(pdf_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def count_pdf_pages(pdf_path: str) -> int:
    from pypdf import PdfReader

    return len(PdfReader(pdf_path).pages)


def render_cover_letter_to_latex(name: str, contact_parts: list[str], date_str: str, company: str, body_text: str) -> str:
    """Same controlled-template approach as render_cv_to_latex: the LLM
    only ever produced `body_text` (already assembled from validated
    structured output) -- everything else is Python string-building with
    mandatory escaping, substituted into cv_templates/cover_letter/standard.tex."""

    template_path = (TEMPLATES_DIR / "cover_letter" / "standard.tex").resolve()
    if TEMPLATES_DIR.resolve() not in template_path.parents:
        raise PathSecurityError("Template path escapes cv_templates/")
    template = template_path.read_text(encoding="utf-8")

    contact_line = " \\quad|\\quad ".join(escape_latex(p) for p in contact_parts if p)
    paragraphs = "\n\n".join(escape_latex(p) for p in body_text.split("\n\n") if p.strip())

    return (
        template
        .replace("{{NAME}}", escape_latex(name))
        .replace("{{CONTACT_LINE}}", contact_line)
        .replace("{{DATE}}", escape_latex(date_str))
        .replace("{{COMPANY}}", escape_latex(company))
        .replace("{{BODY}}", paragraphs)
    )


def compile_cover_letter_pdf(latex_source: str, job_id: int, version_number: int) -> CompileResult:
    settings = get_settings()
    return compile_latex_to_pdf(
        latex_source, settings.application_materials_dir, f"job_{job_id}", f"cover_letter_v{version_number}"
    )
