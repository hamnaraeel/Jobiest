# data/application_materials/

Runtime output from Step 4's cover letter PDF rendering, not source. When
`GET /cover-letters/{id}/download?format=pdf` is requested for the first
time, the letter is compiled here as:

```
data/application_materials/
  job_{job_id}/
    cover_letter_v{version_number}.tex
    cover_letter_v{version_number}.pdf
```

Compilation is lazy -- it only happens on the first PDF download request
for a given version (`GET .../download?format=txt`, the default, never
touches this directory at all, since the letter's text is served directly
from the database). Once compiled, the path is cached on the `CoverLetter`
row so later downloads don't recompile.

This mirrors `data/cvs/README.md` exactly: the `.tex`/`.pdf` files here
are a convenience for direct inspection, not the only copy of the data --
`GET /cover-letters/{id}` always returns the full text from the database
regardless of whether a PDF has ever been compiled.

Gitignored (`career-agent/data/application_materials/*` in the root
`.gitignore`, except this file and `.gitkeep`) since it's generated
per-run. Storage root is configurable via `APPLICATION_MATERIALS_DIR`.

For a checked-in example, see `docs/examples/cover_letter_example.txt`.
