# CV Templates

Each `.tex` file here is a **controlled template** -- the LLM never writes
or sees LaTeX. `app/services/cv_render_service.py` builds each section's
LaTeX from structured `CVContent` data (escaping every piece of text via
`escape_latex()`), then substitutes exactly two placeholders into the
template:

- `{{HEADER_BLOCK}}` -- the candidate's name, tagline, and contact/link
  lines, already joined with `\\`
- `{{BODY}}` -- every included section's rendered LaTeX, concatenated in
  `CVContent.section_order`

No other placeholder substitution happens, and nothing from an AI response
is ever written into the `.tex` file except pre-escaped plain text sitting
inside sections Python already generated -- there is no code path where an
LLM's raw output reaches the LaTeX compiler.

## `ats/ml_engineer.tex`

The default template. Deliberately avoids everything that breaks ATS
parsers or PDF text extraction: no tables, no multi-column layout, no text
boxes, no icons standing in for text, no graphics or photos. Just
`article`-class LaTeX with `\section`-style headings (a bold title + a
rule), plain `itemize` bullet lists, and a centered header block. Only
`geometry` (margins) and `hyperref` (clickable links, `hidelinks` so no
colored boxes appear) are used -- both are part of essentially every LaTeX
installation, including a minimal one (e.g. `basictex` on macOS).

## Adding a new template

1. Add a `.tex` file under a subdirectory here (e.g. `ats/research.tex`)
   with the same two placeholders.
2. Reference it by its path relative to this directory, without the
   extension -- e.g. `"ats/research"` -- as `template_name` in
   `POST /jobs/{job_id}/cv/generate`.
3. Keep it ATS-friendly (no tables/columns/graphics) unless the template
   is explicitly meant for a different purpose (e.g. a design-role
   portfolio CV that a human, not an ATS, will read).
