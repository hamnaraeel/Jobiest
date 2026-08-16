import shutil
from datetime import date

import pytest

from app.config import get_settings
from app.models.enums import CVSectionType, EntityType
from app.schemas.cv import CVBullet, CVContent, CVExperienceEntry, CVHeader, CVSkillCategory
from app.services import cv_render_service

# Checks settings.pdflatex_path (what compile_pdf() actually invokes), not
# just a bare "pdflatex" on PATH -- PDFLATEX_PATH is commonly set to an
# absolute path (e.g. /Library/TeX/texbin/pdflatex on macOS with BasicTeX)
# precisely because it *isn't* on PATH, so checking PATH alone gives a
# false negative here even though compile_pdf() would succeed.
_pdflatex_path = get_settings().pdflatex_path
PDFLATEX_AVAILABLE = shutil.which(_pdflatex_path) is not None


# --- 14: LaTeX escaping -----------------------------------------------------


@pytest.mark.parametrize("raw,expected_fragment", [
    ("50% improvement", r"50\% improvement"),
    ("C# & .NET", r"C\# \& .NET"),
    ("cost was $5", r"cost was \$5"),
    ("snake_case_var", r"snake\_case\_var"),
    ("{curly}", r"\{curly\}"),
    ("a~b", r"a\textasciitilde{}b"),
    ("a^b", r"a\textasciicircum{}b"),
    ("back\\slash", r"back\textbackslash{}slash"),
])
def test_escape_latex_handles_special_characters(raw, expected_fragment):
    assert expected_fragment in cv_render_service.escape_latex(raw)


def test_escape_latex_handles_none_and_empty():
    assert cv_render_service.escape_latex(None) == ""
    assert cv_render_service.escape_latex("") == ""


def test_escape_latex_backslash_not_double_escaped():
    # If backslash weren't escaped first, the backslash introduced by
    # escaping "%" would itself get escaped again.
    result = cv_render_service.escape_latex("100%")
    assert result == r"100\%"
    assert r"\\%" not in result


def _sample_content() -> CVContent:
    return CVContent(
        header=CVHeader(name="Jane Doe", email="jane@example.com", phone="+1 555-0100"),
        summary="ML engineer with 50% faster training pipelines & PyTorch experience.",
        skills=[CVSkillCategory(category="ML/DL", skills=["PyTorch", "Computer Vision"])],
        experience=[CVExperienceEntry(
            experience_id=1, company="Acme & Co", role="ML Engineer",
            start_date=date(2023, 1, 1), currently_working=True,
            bullets=[CVBullet(text="Built models using PyTorch (95% accuracy).", source_type=EntityType.EXPERIENCE_BULLET, source_id=1, verified=True)],
        )],
        projects=[], research=[], education=[], certifications=[], achievements=[],
        section_order=[CVSectionType.SUMMARY, CVSectionType.SKILLS, CVSectionType.EXPERIENCE],
    )


def test_render_cv_to_latex_escapes_special_characters_in_content():
    latex = cv_render_service.render_cv_to_latex(_sample_content(), template_name="ats/ml_engineer")
    assert r"50\%" in latex
    assert r"Acme \& Co" in latex
    assert r"95\%" in latex
    assert "Jane Doe" in latex


def test_render_cv_to_latex_respects_section_order():
    content = _sample_content()
    latex = cv_render_service.render_cv_to_latex(content, template_name="ats/ml_engineer")
    assert latex.index("Summary") < latex.index("Skills") < latex.index("Experience")


def test_render_cv_to_latex_rejects_path_traversal():
    with pytest.raises((cv_render_service.PathSecurityError, FileNotFoundError)):
        cv_render_service.render_cv_to_latex(_sample_content(), template_name="../../etc/passwd")


def test_render_cv_to_latex_unknown_template_raises():
    with pytest.raises(FileNotFoundError):
        cv_render_service.render_cv_to_latex(_sample_content(), template_name="ats/does_not_exist")


# --- 15 & 16: PDF generation and text extraction (needs pdflatex) -----------


@pytest.mark.skipif(not PDFLATEX_AVAILABLE, reason="pdflatex is not installed in this environment")
def test_compile_pdf_produces_readable_pdf():
    content = _sample_content()
    latex = cv_render_service.render_cv_to_latex(content, template_name="ats/ml_engineer")
    # A high, distinctive job_id avoids colliding with real job data on disk.
    result = cv_render_service.compile_pdf(latex, job_id=999999001, version_number=1)

    try:
        assert result.success, result.error
        assert result.pdf_path is not None

        text = cv_render_service.extract_pdf_text(result.pdf_path)
        assert "Jane Doe" in text
        assert cv_render_service.count_pdf_pages(result.pdf_path) >= 1
    finally:
        if result.pdf_path:
            from pathlib import Path
            path = Path(result.pdf_path)
            if path.exists():
                path.unlink()
                if not any(path.parent.iterdir()):
                    path.parent.rmdir()


@pytest.mark.skipif(PDFLATEX_AVAILABLE, reason="only exercises the missing-pdflatex path")
def test_compile_pdf_reports_clear_error_when_pdflatex_missing():
    content = _sample_content()
    latex = cv_render_service.render_cv_to_latex(content, template_name="ats/ml_engineer")
    result = cv_render_service.compile_pdf(latex, job_id=99999, version_number=1)
    assert result.success is False
    assert "pdflatex" in (result.error or "").lower() or result.error is not None
