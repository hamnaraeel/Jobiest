# data/backups/

Local backups created by `python -m app.cli backup` (run from
`career-agent/backend/`), not source. Each run writes to:

```
data/backups/
  {UTC timestamp}/
    database.sql       full pg_dump of the configured database
    metadata.json       non-secret settings snapshot
    browser_profile/    only with --include-browser-profile
```

`DATABASE_URL` and `OPENAI_API_KEY` are never written to `metadata.json`
(they're excluded explicitly, since `DATABASE_URL` can contain
credentials). The browser profile (cookies/session state) is excluded by
default too -- pass `--include-browser-profile` if you specifically want
it backed up.

Gitignored (`career-agent/data/backups/*` in the root `.gitignore`,
except this file and `.gitkeep`) since backups contain your actual
career/application data.
