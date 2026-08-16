# data/application_sessions/

Runtime output from Step 5's browser sessions, not source. When
`BROWSER_SCREENSHOTS=true`, `browser_manager.take_screenshot()` writes
here as:

```
data/application_sessions/
  {application_id}/
    {name}.png
```

Screenshots are off by default (`take_screenshot()` is a no-op unless
`BROWSER_SCREENSHOTS=true`) and are never exposed through any API
endpoint -- they exist only for local debugging of the automation itself,
not as part of the application record.

Gitignored (`career-agent/data/application_sessions/*` in the root
`.gitignore`, except this file and `.gitkeep`) since it's generated
per-run and may contain screenshots of pages you applied to. Storage root
is configurable via `APPLICATION_SESSIONS_DIR`.
