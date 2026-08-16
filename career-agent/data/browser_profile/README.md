# data/browser_profile/

Persistent Playwright/Chromium user-data directory for Step 5's browser
automation, not source. `browser_manager.start_session()` launches every
browser session against this same directory
(`launch_persistent_context(...)`), so cookies and local storage survive
across separate application runs -- this is what lets you log in to a
site manually once and stay logged in later, since the agent itself never
automates login (see `docs/browser-application-assistant.md`).

Only one browser session can be open against this directory at a time
(Chromium locks a persistent profile directory to a single running
instance); `browser_manager` never launches a second one concurrently.

This directory's contents are gitignored
(`career-agent/data/browser_profile/*` in the root `.gitignore`, except
this file and `.gitkeep`) since it's machine-local runtime state, not
something to check in -- it may contain session cookies for whatever
sites you've used the assistant on. The storage root is configurable via
`BROWSER_PROFILE_DIR` (see `.env.example`).
