# data/cvs/

Runtime output from Step 3's CV generation pipeline, not source. When
`POST /jobs/{job_id}/cv/generate` compiles a PDF, it writes here as:

```
data/cvs/
  job_{job_id}/
    cv_v{version_number}.tex
    cv_v{version_number}.pdf
```

The `.tex` file is the exact LaTeX Python rendered from that CV version's
structured content (see `cv_templates/README.md`); the `.pdf` is what
`pdflatex` compiled from it. Both are also stored/served independently of
the filesystem via the `CVVersion` row itself (`GET /cvs/{id}` returns the
structured content and `latex_source`; `GET /cvs/{id}/download` streams
the PDF) -- these files are a convenience for direct inspection, not the
only copy of the data.

This directory's contents are gitignored (`career-agent/data/cvs/*` in the
root `.gitignore`, except this file and `.gitkeep`) since they're
generated per-run, not something to check in. The storage root is
configurable via `CV_STORAGE_DIR` (see `.env.example`).

For a checked-in example of what ends up here, see
`docs/examples/cv_example.json` and `docs/examples/cv_example.tex`.
